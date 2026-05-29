package collector

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/config"
)

// TestRun_DeliversShutdownWindow drives Run with a fast poll interval and a
// context that is cancelled shortly after the first sample is collected.
// The loop must compute a FINAL partial window on ctx.Done() and hand it to
// onWindow — this is the window that the shutdown-flush bug used to drop.
func TestRun_DeliversShutdownWindow(t *testing.T) {
	// Poll fast (1s, the minimum granularity Run accepts) so at least one
	// sample is collected before we cancel. Flush is set far out so the
	// ONLY window delivered is the shutdown one.
	cfg := config.CollectorConfig{PollIntervalSec: 1, FlushIntervalSec: 3600}

	var mu sync.Mutex
	var windows []FlowWindow
	onWindow := func(w FlowWindow) {
		mu.Lock()
		windows = append(windows, w)
		mu.Unlock()
	}

	sampleCh := make(chan struct{}, 8)
	onSample := func(Sample) {
		select {
		case sampleCh <- struct{}{}:
		default:
		}
	}

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- Run(ctx, cfg, onWindow, onSample) }()

	// Wait for at least one sample so the shutdown window is non-empty
	// (Run only emits a final window when len(samples) > 0).
	select {
	case <-sampleCh:
	case <-time.After(5 * time.Second):
		cancel()
		t.Fatal("timed out waiting for first sample")
	}

	cancel()

	select {
	case err := <-done:
		if err != context.Canceled {
			t.Fatalf("expected context.Canceled, got %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("Run did not return after cancel")
	}

	mu.Lock()
	defer mu.Unlock()
	if len(windows) != 1 {
		t.Fatalf("expected exactly 1 (shutdown) window, got %d", len(windows))
	}
	if windows[0].WindowEnd.Before(windows[0].WindowStart) {
		t.Errorf("shutdown window has end before start: %+v", windows[0])
	}
}

// TestRun_NoShutdownWindowWhenNoSamples confirms the loop does not emit an
// empty window when cancelled before any sample is collected — that would
// push a meaningless zero-flow window every shutdown.
func TestRun_NoShutdownWindowWhenNoSamples(t *testing.T) {
	cfg := config.CollectorConfig{PollIntervalSec: 3600, FlushIntervalSec: 3600}

	var mu sync.Mutex
	var count int
	onWindow := func(FlowWindow) {
		mu.Lock()
		count++
		mu.Unlock()
	}

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- Run(ctx, cfg, onWindow, nil) }()

	// Cancel immediately — no poll tick will have fired.
	cancel()

	select {
	case err := <-done:
		if err != context.Canceled {
			t.Fatalf("expected context.Canceled, got %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("Run did not return after cancel")
	}

	mu.Lock()
	defer mu.Unlock()
	if count != 0 {
		t.Errorf("expected no windows with zero samples, got %d", count)
	}
}
