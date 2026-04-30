// Package autotimer detects sustained flow and suggests starting a timer.
package autotimer

import (
	"context"
	"fmt"
	"log"

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

// Tracker watches flow windows and suggests timer starts when sustained
// high flow is detected without a running timer.
type Tracker struct {
	client             *client.Client
	consecutiveHighFlow int
	lastSuggestedCategory string
}

// NewTracker creates a new auto-timer suggestion tracker.
func NewTracker(c *client.Client) *Tracker {
	return &Tracker{client: c}
}

// OnFlowWindow is called after each flow window computation.
// It checks if sustained high flow warrants a timer suggestion.
func (t *Tracker) OnFlowWindow(ctx context.Context, w collector.FlowWindow) {
	if w.FlowScore >= FlowThreshold {
		t.consecutiveHighFlow++
	} else {
		t.consecutiveHighFlow = 0
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

	notify.Send(
		"Start timer?",
		fmt.Sprintf("You've been focused on %s for %d minutes. Start tracking \"%s\"?",
			w.DominantCategory, t.consecutiveHighFlow, suggestion.ProjectName),
	)
}
