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

func TestShield_DriftFiresExactlyOnceAtLeave(t *testing.T) {
	var fired []DriftEvent
	tracker := NewTracker(func(ev DriftEvent) { fired = append(fired, ev) })

	start := time.Date(2026, 4, 30, 12, 0, 0, 0, time.UTC)

	// Enter Twitter at t=0, stay there past the 30s threshold,
	// then leave to a non-distraction app at t=45.
	for i := 0; i <= 40; i += 5 {
		tracker.OnSample(sample(start, i, "com.twitter.twitter-mac"), true)
	}
	tracker.OnSample(sample(start, 45, "com.apple.dt.Xcode"), true)

	// Exactly ONE drift event per session — the previous
	// implementation emitted at threshold-crossing AND at leave,
	// double-posting to the API. Locks in that the API now sees
	// one record per drift session, with the FINAL duration (45s),
	// not an intermediate threshold-crossing duration.
	if len(fired) != 1 {
		t.Fatalf("expected exactly 1 drift event per session, got %d: %+v", len(fired), fired)
	}
	if fired[0].BundleID != "com.twitter.twitter-mac" {
		t.Errorf("wrong bundle in drift: %s", fired[0].BundleID)
	}
	if fired[0].Duration != 45*time.Second {
		t.Errorf("expected final duration 45s, got %s", fired[0].Duration)
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

func TestShield_LongDriftDoesNotEmitOnEverySample(t *testing.T) {
	// Regression guard: the previous implementation emitted at the
	// threshold-crossing sample, which meant a 5-second-cadence
	// collector hitting the 30..35s window would fire emitDrift.
	// On a 1-second-cadence collector that window would have fired
	// emitDrift 5 separate times (30,31,32,33,34s), each landing as
	// a separate API record. Even with the realistic 5s cadence,
	// the leave-sample's emit was a second copy. Both regressed.
	var fired []DriftEvent
	tracker := NewTracker(func(ev DriftEvent) { fired = append(fired, ev) })

	start := time.Date(2026, 4, 30, 12, 0, 0, 0, time.UTC)

	// 5-minute drift, sampled every 1s. Old code would have emitted
	// at 30s, 31s, 32s, 33s, 34s (5 times in the 5s window) plus
	// once at leave = 6 events. New code emits exactly once at leave.
	for i := 0; i <= 300; i++ {
		tracker.OnSample(sample(start, i, "com.twitter.twitter-mac"), true)
	}
	tracker.OnSample(sample(start, 301, "com.apple.dt.Xcode"), true)

	if len(fired) != 1 {
		t.Fatalf("expected exactly 1 drift event regardless of sample cadence, got %d", len(fired))
	}
	if fired[0].Duration != 301*time.Second {
		t.Errorf("expected final 301s duration, got %s", fired[0].Duration)
	}
}

// formatDriftMessage builds the body of the system notification
// fired when distraction crosses threshold. Replaces an earlier
// version that said "for 30s" verbatim and rendered raw bundle
// IDs — both lied about reality when threshold ≠ 30s or the app
// had a friendly label.

func TestFormatDriftMessage_KnownBundleUsesFriendlyLabel(t *testing.T) {
	got := formatDriftMessage("com.twitter.twitter-mac", 45*time.Second)
	want := "You've been on Twitter for 45s while your timer is running."
	if got != want {
		t.Errorf("expected friendly label, got %q", got)
	}
}

func TestFormatDriftMessage_UnknownBundleFallsBackToTrailingSegment(t *testing.T) {
	// bundle.ShortLabel falls back to the last reverse-DNS segment
	// for unknown ids — the message stays readable rather than
	// dumping "com.unknown.SomeApp" verbatim.
	got := formatDriftMessage("com.unknown.SomeApp", 30*time.Second)
	if got != "You've been on SomeApp for 30s while your timer is running." {
		t.Errorf("expected fallback segment, got %q", got)
	}
}

func TestFormatDriftMessage_RoundsDurationToSecond(t *testing.T) {
	// Sub-second precision in a system notification reads as
	// noise. duration.Round(time.Second) keeps the message clean.
	got := formatDriftMessage("com.spotify.client", 35*time.Second+200*time.Millisecond)
	if got != "You've been on Spotify for 35s while your timer is running." {
		t.Errorf("expected rounded duration, got %q", got)
	}
}

func TestFormatDriftMessage_ReflectsActualThresholdNot30sLiteral(t *testing.T) {
	// The previous implementation hardcoded "for 30s" regardless
	// of the actual elapsed time. Pin the dynamic version: a 90s
	// drift should say "for 1m30s", not "for 30s".
	got := formatDriftMessage("com.twitter.twitter-mac", 90*time.Second)
	if got != "You've been on Twitter for 1m30s while your timer is running." {
		t.Errorf("expected actual elapsed time, got %q", got)
	}
}
