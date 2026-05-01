// Package autotimer detects sustained flow and suggests starting a timer.
package autotimer

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/client"
	"github.com/ahmedElghable/beats/daemon/internal/collector"
	"github.com/ahmedElghable/beats/daemon/internal/notify"
)

const (
	// MinConsecutiveHighFlow is the number of consecutive high-flow windows
	// required before suggesting a timer (8 minutes = 8 windows at 1/min).
	MinConsecutiveHighFlow = 8
	// FlowThreshold is the minimum flow score to count as "high flow".
	FlowThreshold = 0.7
)

// Suggester is the slice of the API client the tracker actually needs. We
// take an interface (instead of the concrete *client.Client) so tests can
// inject a fake without spinning up an HTTP server. *client.Client already
// satisfies this; nothing changes for callers.
type Suggester interface {
	SuggestTimer(ctx context.Context, w client.FlowWindowRequest) (*client.AutoTimerSuggestion, error)
}

// Notifier is the side-effect side of the tracker — what to do when a
// suggestion fires. Defaults to notify.Send, but tests pass a capturing
// closure to avoid firing real OS notifications.
type Notifier func(title, body string)

// Tracker watches flow windows and suggests timer starts when sustained
// high flow is detected without a running timer.
type Tracker struct {
	client                Suggester
	notify                Notifier
	consecutiveHighFlow   int
	firstHighFlowStart    time.Time // window_start of the first window in the current high-flow streak
	lastSuggestedCategory string
}

// NewTracker creates a new auto-timer suggestion tracker that posts to the
// given API client and fires desktop notifications via notify.Send.
func NewTracker(c Suggester) *Tracker {
	return &Tracker{client: c, notify: notify.Send}
}

// NewTrackerWithNotifier is the testable form: lets the caller intercept
// the notification side effect.
func NewTrackerWithNotifier(c Suggester, n Notifier) *Tracker {
	if n == nil {
		n = notify.Send
	}
	return &Tracker{client: c, notify: n}
}

// OnFlowWindow is called after each flow window computation.
// It checks if sustained high flow warrants a timer suggestion.
func (t *Tracker) OnFlowWindow(ctx context.Context, w collector.FlowWindow) {
	if w.FlowScore >= FlowThreshold {
		// Pin the start of the streak when consecutive count
		// transitions from zero — used to compute actual elapsed
		// minutes for the notification body, regardless of
		// FlushIntervalSec. The previous code used the window
		// count as a stand-in for minutes, which only worked when
		// FlushIntervalSec was the default 60s.
		if t.consecutiveHighFlow == 0 {
			t.firstHighFlowStart = w.WindowStart
		}
		t.consecutiveHighFlow++
	} else {
		t.consecutiveHighFlow = 0
		t.firstHighFlowStart = time.Time{}
		t.lastSuggestedCategory = ""
		return
	}

	if t.consecutiveHighFlow < MinConsecutiveHighFlow {
		return
	}

	// Don't re-suggest for the same category
	if w.DominantCategory == t.lastSuggestedCategory {
		return
	}

	// Ask API if we should suggest
	suggestion, err := t.client.SuggestTimer(ctx, client.FlowWindowRequest{
		WindowStart:      w.WindowStart,
		WindowEnd:        w.WindowEnd,
		FlowScore:        w.FlowScore,
		CadenceScore:     w.CadenceScore,
		CoherenceScore:   w.CoherenceScore,
		CategoryFitScore: w.CategoryFitScore,
		IdleFraction:     w.IdleFraction,
		DominantBundleID: w.DominantBundleID,
		DominantCategory: w.DominantCategory,
		ContextSwitches:  w.ContextSwitches,
		ActiveProjectID:  w.ActiveProjectID,
		// Editor heartbeat fields. The API's /suggest-timer
		// matches editor_repo against project.autostart_repos
		// before falling back to category — without these
		// forwarded the API can only category-match, defeating
		// the per-repo auto-start design (commit 69da1f5).
		EditorRepo:     w.EditorRepo,
		EditorBranch:   w.EditorBranch,
		EditorLanguage: w.EditorLanguage,
	})
	if err != nil {
		log.Printf("autotimer: suggest API call failed: %v", err)
		return
	}

	if !suggestion.ShouldSuggest {
		return
	}

	t.lastSuggestedCategory = w.DominantCategory
	log.Printf("autotimer: suggesting timer for %q (project: %s)", suggestion.ProjectName, suggestion.ProjectID)

	// Compute actual elapsed minutes from the first high-flow
	// window's start. Falls back to the count (which equals minutes
	// at the default 60s flush) if firstHighFlowStart was somehow
	// never set — defensive belt for a flow that should have set it.
	elapsedMin := t.consecutiveHighFlow
	if !t.firstHighFlowStart.IsZero() {
		elapsedMin = int(w.WindowEnd.Sub(t.firstHighFlowStart).Minutes())
		if elapsedMin < 1 {
			elapsedMin = 1
		}
	}
	t.notify(
		"Start timer?",
		fmt.Sprintf("You've been focused on %s for %d minutes. Start tracking \"%s\"?",
			w.DominantCategory, elapsedMin, suggestion.ProjectName),
	)
}
