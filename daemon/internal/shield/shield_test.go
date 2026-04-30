package shield

import (
	"testing"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/collector"
)

// sample builds a collector.Sample at offset seconds past a fixed start.
// All shield logic is time-based, so we don't use real time.Now() in tests.
func sample(start time.Time, offsetSec int, bundle string) collector.Sample {
	return collector.Sample{
		CollectedAt: start.Add(time.Duration(offsetSec) * time.Second),
		BundleID:    bundle,
		AppName:     bundle,
	}
}

func TestShield_NoTimer_NoDrift(t *testing.T) {
	var fired []DriftEvent
	tracker := NewTracker(func(ev DriftEvent) { fired = append(fired, ev) })

	start := time.Date(2026, 4, 30, 12, 0, 0, 0, time.UTC)
	for i := 0; i < 60; i += 5 {
		tracker.OnSample(sample(start, i, "com.twitter.twitter-mac"), false)
	}
	if len(fired) != 0 {
		t.Errorf("drift fired with no timer running: %d events", len(fired))
	}
}

func TestShield_DriftFiresAfterThreshold(t *testing.T) {
	var fired []DriftEvent
	tracker := NewTracker(func(ev DriftEvent) { fired = append(fired, ev) })

	start := time.Date(2026, 4, 30, 12, 0, 0, 0, time.UTC)

	// Enter Twitter at t=0, stay there past the 30s threshold.
	for i := 0; i <= 35; i += 5 {
		tracker.OnSample(sample(start, i, "com.twitter.twitter-mac"), true)
	}

	if len(fired) == 0 {
		t.Fatal("expected at least one drift event after threshold")
	}
	if fired[0].BundleID != "com.twitter.twitter-mac" {
		t.Errorf("wrong bundle in drift: %s", fired[0].BundleID)
	}
}

func TestShield_DriftDoesNotFireBelowThreshold(t *testing.T) {
	var fired []DriftEvent
	tracker := NewTracker(func(ev DriftEvent) { fired = append(fired, ev) })

	start := time.Date(2026, 4, 30, 12, 0, 0, 0, time.UTC)

	// 20 seconds of Twitter, then back to a non-distraction.
	tracker.OnSample(sample(start, 0, "com.twitter.twitter-mac"), true)
	tracker.OnSample(sample(start, 10, "com.twitter.twitter-mac"), true)
	tracker.OnSample(sample(start, 20, "com.twitter.twitter-mac"), true)
	tracker.OnSample(sample(start, 25, "com.apple.dt.Xcode"), true)

	if len(fired) != 0 {
		t.Errorf("drift fired below threshold: %d events", len(fired))
	}
}

func TestShield_NonDistractionApp_NoDrift(t *testing.T) {
	var fired []DriftEvent
	tracker := NewTracker(func(ev DriftEvent) { fired = append(fired, ev) })

	start := time.Date(2026, 4, 30, 12, 0, 0, 0, time.UTC)
	for i := 0; i <= 120; i += 5 {
		tracker.OnSample(sample(start, i, "com.apple.dt.Xcode"), true)
	}
	if len(fired) != 0 {
		t.Errorf("drift fired on non-distraction app: %d events", len(fired))
	}
}

func TestShield_TimerStops_ResetsState(t *testing.T) {
	var fired []DriftEvent
	tracker := NewTracker(func(ev DriftEvent) { fired = append(fired, ev) })

	start := time.Date(2026, 4, 30, 12, 0, 0, 0, time.UTC)

	// In Twitter for 25s with timer running (below threshold).
	tracker.OnSample(sample(start, 0, "com.twitter.twitter-mac"), true)
	tracker.OnSample(sample(start, 25, "com.twitter.twitter-mac"), true)

	// Timer stops — tracker resets. Now another 25s on Twitter shouldn't
	// merge with the previous run-up.
	tracker.OnSample(sample(start, 30, "com.twitter.twitter-mac"), false)

	// Timer back on. Re-enter Twitter for 20s — still below threshold.
	tracker.OnSample(sample(start, 35, "com.twitter.twitter-mac"), true)
	tracker.OnSample(sample(start, 50, "com.twitter.twitter-mac"), true)
	tracker.OnSample(sample(start, 55, "com.apple.dt.Xcode"), true)

	if len(fired) != 0 {
		t.Errorf("drift fired across a timer-stop boundary: %d events", len(fired))
	}
}
