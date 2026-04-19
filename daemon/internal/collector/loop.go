package collector

import (
	"context"
	"errors"
	"log"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/config"
)

// Run starts the signal collection loop. It polls the desktop state at
// PollIntervalSec and computes + emits a FlowWindow every FlushIntervalSec.
//
// The onWindow callback receives each computed FlowWindow. It runs synchronously
// on the loop goroutine — keep it fast (the API POST is acceptable).
//
// Run blocks until ctx is cancelled.
func Run(ctx context.Context, cfg config.CollectorConfig, onWindow func(FlowWindow)) error {
	pollInterval := time.Duration(cfg.PollIntervalSec) * time.Second
	flushInterval := time.Duration(cfg.FlushIntervalSec) * time.Second

	if pollInterval <= 0 {
		pollInterval = 5 * time.Second
	}
	if flushInterval <= 0 {
		flushInterval = 60 * time.Second
	}

	// Attempt to start the input event tap (cadence tracking).
	getAndReset, stop, err := StartEventTap()
	hasEventTap := err == nil
	if err != nil {
		if errors.Is(err, ErrEventTapNotAvailable) {
			log.Println("collector: input event tap not available, cadence will default to 0.5")
		} else {
			log.Printf("collector: event tap error: %v", err)
		}
	}
	if stop != nil {
		defer stop()
	}

	var samples []Sample
	windowStart := time.Now().UTC()

	pollTicker := time.NewTicker(pollInterval)
	defer pollTicker.Stop()

	flushTicker := time.NewTicker(flushInterval)
	defer flushTicker.Stop()

	log.Printf("collector: polling every %s, flushing every %s", pollInterval, flushInterval)

	for {
		select {
		case <-ctx.Done():
			// Final flush on shutdown
			if len(samples) > 0 {
				w := ComputeFlowWindow(samples, windowStart, time.Now().UTC(), "", "")
				onWindow(w)
			}
			return ctx.Err()

		case <-pollTicker.C:
			s := collectSample(hasEventTap, getAndReset)
			samples = append(samples, s)

		case now := <-flushTicker.C:
			if len(samples) == 0 {
				windowStart = now.UTC()
				continue
			}
			windowEnd := now.UTC()
			w := ComputeFlowWindow(samples, windowStart, windowEnd, "", "")
			onWindow(w)

			// Reset for next window
			samples = samples[:0]
			windowStart = windowEnd
		}
	}
}

// collectSample takes a single observation of the desktop state.
func collectSample(hasEventTap bool, getAndReset func() int64) Sample {
	bundleID, appName := FrontmostApp()
	idle := IdleSeconds()

	var eventCount int64 = -1
	if hasEventTap && getAndReset != nil {
		eventCount = getAndReset()
	}

	return Sample{
		CollectedAt: time.Now().UTC(),
		BundleID:    bundleID,
		AppName:     appName,
		IdleSeconds: idle,
		EventCount:  eventCount,
	}
}
