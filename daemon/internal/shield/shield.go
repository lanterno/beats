// Package shield detects distraction apps during active timers and emits drift events.
package shield

import (
	"fmt"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/bundle"
	"github.com/ahmedElghable/beats/daemon/internal/collector"
	"github.com/ahmedElghable/beats/daemon/internal/notify"
)

// DefaultDistractionBundles are bundle IDs considered distracting during work.
var DefaultDistractionBundles = map[string]bool{
	"com.twitter.twitter-mac": true,
	"com.spotify.client":      true,
	"com.apple.Music":         true,
	"com.netflix.Netflix":     true,
	"tv.twitch.studio":        true,
	"com.hnc.Discord":         true, // when timer running on non-communication project
}

// DistractionBrowserPatterns are URL patterns that indicate browser-based distractions.
// These would need browser extension integration to detect — included for future use.
var DistractionBrowserPatterns = []string{
	"twitter.com", "x.com", "reddit.com", "youtube.com",
	"news.ycombinator.com", "instagram.com", "tiktok.com",
}

// DriftEvent represents a detected distraction period.
type DriftEvent struct {
	StartedAt time.Time
	Duration  time.Duration
	BundleID  string
	AppName   string
}

// Tracker monitors for distraction apps while a timer is running.
type Tracker struct {
	distractions        map[string]bool
	distractionStart    time.Time
	distractionApp      string
	inDistraction       bool
	notifiedThisSession bool          // notification already fired for this session — don't re-spam
	threshold           time.Duration // how long before it counts as drift
	onDrift             func(DriftEvent)
}

// NewTracker creates a distraction shield tracker.
// onDrift is called when a distraction period exceeds the threshold.
func NewTracker(onDrift func(DriftEvent)) *Tracker {
	return &Tracker{
		distractions: DefaultDistractionBundles,
		threshold:    30 * time.Second,
		onDrift:      onDrift,
	}
}

// OnSample is called with each desktop sample. It checks if the user is
// in a distraction app while a timer is running.
func (t *Tracker) OnSample(sample collector.Sample, timerRunning bool) {
	if !timerRunning {
		t.reset()
		return
	}

	isDistraction := t.distractions[sample.BundleID]

	if isDistraction && !t.inDistraction {
		// Entering distraction
		t.inDistraction = true
		t.distractionStart = sample.CollectedAt
		t.distractionApp = sample.BundleID
	} else if !isDistraction && t.inDistraction {
		// Leaving distraction — emit ONE drift event with the final
		// duration. The notification has already fired at the
		// threshold-crossing sample (below); the API record only
		// lands here so each drift session produces exactly one
		// FlowWindow with category="drift".
		duration := sample.CollectedAt.Sub(t.distractionStart)
		if duration >= t.threshold {
			t.emitDrift(duration)
		}
		t.reset()
	}
	// While still in distraction, fire the user-facing notification
	// once when crossing threshold. NO emitDrift here — that would
	// double-post (once at threshold-crossing, once at leave) for
	// every drift session longer than the threshold. The 5s window
	// is wide enough that a 5s-cadence collector hits exactly one
	// sample inside it.
	if t.inDistraction && !t.notifiedThisSession {
		duration := sample.CollectedAt.Sub(t.distractionStart)
		if duration >= t.threshold {
			sendDriftNotification(t.distractionApp, duration)
			t.notifiedThisSession = true
		}
	}
}

func (t *Tracker) emitDrift(duration time.Duration) {
	if t.onDrift != nil {
		t.onDrift(DriftEvent{
			StartedAt: t.distractionStart,
			Duration:  duration,
			BundleID:  t.distractionApp,
		})
	}
}

func (t *Tracker) reset() {
	t.inDistraction = false
	t.notifiedThisSession = false
	t.distractionStart = time.Time{}
	t.distractionApp = ""
}

// sendDriftNotification fires the OS-level "drift detected" alert
// when distraction duration crosses the threshold. The message is
// rendered by formatDriftMessage so the body can be unit-tested
// without shelling out to osascript / notify-send.
func sendDriftNotification(bundleID string, duration time.Duration) {
	notify.Send("Drift detected", formatDriftMessage(bundleID, duration))
}

// formatDriftMessage builds the body of the drift notification.
// Renders the human-readable bundle name (e.g. "Twitter" instead
// of "com.twitter.twitter-mac") and the actual elapsed seconds
// rather than hardcoding the threshold — the previous version said
// "for 30s" verbatim, which both showed a developer-style bundle id
// and lied about the duration when threshold ≠ 30s.
func formatDriftMessage(bundleID string, duration time.Duration) string {
	return fmt.Sprintf("You've been on %s for %s while your timer is running.",
		bundle.ShortLabel(bundleID), duration.Round(time.Second))
}
