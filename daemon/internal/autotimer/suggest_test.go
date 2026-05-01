package autotimer

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/client"
	"github.com/ahmedElghable/beats/daemon/internal/collector"
)

// fakeSuggester records every SuggestTimer call and returns a programmable
// response. Sufficient for verifying the tracker's state-machine without
// spinning up an HTTP server.
type fakeSuggester struct {
	calls    int
	response client.AutoTimerSuggestion
	err      error
}

func (f *fakeSuggester) SuggestTimer(_ context.Context, _ client.FlowWindowRequest) (*client.AutoTimerSuggestion, error) {
	f.calls++
	if f.err != nil {
		return nil, f.err
	}
	r := f.response
	return &r, nil
}

// notifications captures the (title, body) tuple of each notify call.
type notifications struct {
	calls [][2]string
}

func (n *notifications) record(title, body string) {
	n.calls = append(n.calls, [2]string{title, body})
}

// window builds a FlowWindow at offset minutes past a fixed start with the
// given score and dominant category. The other fields are filler — the
// state machine only branches on score and category.
func window(start time.Time, offsetMin int, score float64, category string) collector.FlowWindow {
	return collector.FlowWindow{
		WindowStart:      start.Add(time.Duration(offsetMin) * time.Minute),
		WindowEnd:        start.Add(time.Duration(offsetMin+1) * time.Minute),
		FlowScore:        score,
		DominantCategory: category,
	}
}

// windowSec is window's variant for non-default flush cadences. Used by
// the "30s flush" test below to produce 8 high-flow windows that span
// only 4 minutes of wall-clock time (not 8) — would lie under the old
// "%d minutes = %d windows" formatting.
func windowSec(start time.Time, offsetSec, durationSec int, score float64, category string) collector.FlowWindow {
	return collector.FlowWindow{
		WindowStart:      start.Add(time.Duration(offsetSec) * time.Second),
		WindowEnd:        start.Add(time.Duration(offsetSec+durationSec) * time.Second),
		FlowScore:        score,
		DominantCategory: category,
	}
}

func TestTracker_BelowThreshold_NoApiCall(t *testing.T) {
	api := &fakeSuggester{response: client.AutoTimerSuggestion{ShouldSuggest: true}}
	notif := &notifications{}
	tr := NewTrackerWithNotifier(api, notif.record)

	start := time.Date(2026, 4, 30, 9, 0, 0, 0, time.UTC)
	for i := 0; i < 12; i++ {
		tr.OnFlowWindow(context.Background(), window(start, i, 0.5, "coding"))
	}
	if api.calls != 0 {
		t.Errorf("expected 0 API calls under threshold, got %d", api.calls)
	}
	if len(notif.calls) != 0 {
		t.Errorf("expected 0 notifications, got %d", len(notif.calls))
	}
}

func TestTracker_BelowMinConsecutive_NoApiCall(t *testing.T) {
	// Score above threshold but only 5 consecutive windows — under
	// MinConsecutiveHighFlow (8). Should not call the API yet.
	api := &fakeSuggester{response: client.AutoTimerSuggestion{ShouldSuggest: true}}
	notif := &notifications{}
	tr := NewTrackerWithNotifier(api, notif.record)

	start := time.Date(2026, 4, 30, 9, 0, 0, 0, time.UTC)
	for i := 0; i < MinConsecutiveHighFlow-1; i++ {
		tr.OnFlowWindow(context.Background(), window(start, i, 0.85, "coding"))
	}
	if api.calls != 0 {
		t.Errorf("expected 0 API calls below MinConsecutiveHighFlow, got %d", api.calls)
	}
}

func TestTracker_FiresAfterMinConsecutive(t *testing.T) {
	api := &fakeSuggester{
		response: client.AutoTimerSuggestion{
			ShouldSuggest: true,
			ProjectID:     "proj-1",
			ProjectName:   "Beats",
		},
	}
	notif := &notifications{}
	tr := NewTrackerWithNotifier(api, notif.record)

	start := time.Date(2026, 4, 30, 9, 0, 0, 0, time.UTC)
	for i := 0; i < MinConsecutiveHighFlow; i++ {
		tr.OnFlowWindow(context.Background(), window(start, i, 0.85, "coding"))
	}
	if api.calls != 1 {
		t.Errorf("expected exactly 1 API call after threshold, got %d", api.calls)
	}
	if len(notif.calls) != 1 {
		t.Errorf("expected 1 notification, got %d", len(notif.calls))
	}
	if notif.calls[0][0] != "Start timer?" {
		t.Errorf("unexpected notification title: %q", notif.calls[0][0])
	}
}

func TestTracker_DropBelowThreshold_ResetsAndAllowsRetrigger(t *testing.T) {
	// Sustained flow → suggestion fires → score drops → state resets →
	// another sustained run should fire a fresh suggestion (even with the
	// same category, because the reset cleared lastSuggestedCategory).
	api := &fakeSuggester{
		response: client.AutoTimerSuggestion{ShouldSuggest: true, ProjectName: "Beats"},
	}
	notif := &notifications{}
	tr := NewTrackerWithNotifier(api, notif.record)

	start := time.Date(2026, 4, 30, 9, 0, 0, 0, time.UTC)
	for i := 0; i < MinConsecutiveHighFlow; i++ {
		tr.OnFlowWindow(context.Background(), window(start, i, 0.85, "coding"))
	}
	// Score drops — should reset.
	tr.OnFlowWindow(context.Background(), window(start, 9, 0.4, "coding"))
	// Another sustained run.
	for i := 10; i < 10+MinConsecutiveHighFlow; i++ {
		tr.OnFlowWindow(context.Background(), window(start, i, 0.85, "coding"))
	}
	if api.calls != 2 {
		t.Errorf("expected 2 API calls (one per sustained run), got %d", api.calls)
	}
}

func TestTracker_SameCategoryAfterFire_NoSecondCall(t *testing.T) {
	// Once a suggestion fires for "coding", subsequent high-flow windows
	// in the same category should NOT trigger a second API call until the
	// score drops below threshold (which resets the category memo).
	api := &fakeSuggester{
		response: client.AutoTimerSuggestion{ShouldSuggest: true, ProjectName: "Beats"},
	}
	tr := NewTrackerWithNotifier(api, func(_, _ string) {})

	start := time.Date(2026, 4, 30, 9, 0, 0, 0, time.UTC)
	// Warm up to threshold (fires once).
	for i := 0; i < MinConsecutiveHighFlow; i++ {
		tr.OnFlowWindow(context.Background(), window(start, i, 0.85, "coding"))
	}
	// 20 more windows in the same category — no new calls.
	for i := MinConsecutiveHighFlow; i < MinConsecutiveHighFlow+20; i++ {
		tr.OnFlowWindow(context.Background(), window(start, i, 0.85, "coding"))
	}
	if api.calls != 1 {
		t.Errorf("expected to stay at 1 API call for same category, got %d", api.calls)
	}
}

func TestTracker_DifferentCategoryAfterFire_DoesCallAgain(t *testing.T) {
	// Suggestion fires for "coding". Then the dominant category switches
	// to "design" while flow stays high. The new category should trigger
	// a fresh API call.
	api := &fakeSuggester{
		response: client.AutoTimerSuggestion{ShouldSuggest: true},
	}
	tr := NewTrackerWithNotifier(api, func(_, _ string) {})

	start := time.Date(2026, 4, 30, 9, 0, 0, 0, time.UTC)
	for i := 0; i < MinConsecutiveHighFlow; i++ {
		tr.OnFlowWindow(context.Background(), window(start, i, 0.85, "coding"))
	}
	// Switch category while staying above threshold.
	tr.OnFlowWindow(context.Background(), window(start, MinConsecutiveHighFlow, 0.85, "design"))
	if api.calls != 2 {
		t.Errorf("expected 2 API calls across category switch, got %d", api.calls)
	}
}

func TestTracker_ApiSaysNoSuggest_NoNotification(t *testing.T) {
	// API can return ShouldSuggest=false (e.g. category doesn't match any
	// project's autostart_repos). The tracker should call but not notify.
	api := &fakeSuggester{response: client.AutoTimerSuggestion{ShouldSuggest: false}}
	notif := &notifications{}
	tr := NewTrackerWithNotifier(api, notif.record)

	start := time.Date(2026, 4, 30, 9, 0, 0, 0, time.UTC)
	for i := 0; i < MinConsecutiveHighFlow; i++ {
		tr.OnFlowWindow(context.Background(), window(start, i, 0.85, "coding"))
	}
	if api.calls != 1 {
		t.Errorf("expected 1 API call, got %d", api.calls)
	}
	if len(notif.calls) != 0 {
		t.Errorf("expected 0 notifications when API says not to suggest, got %d", len(notif.calls))
	}
}

func TestTracker_ApiError_IsSwallowed(t *testing.T) {
	// A failed SuggestTimer call shouldn't crash the tracker or fire a
	// notification. Should also not memo the category — next window's
	// API call gets retried.
	api := &fakeSuggester{err: errors.New("boom")}
	notif := &notifications{}
	tr := NewTrackerWithNotifier(api, notif.record)

	start := time.Date(2026, 4, 30, 9, 0, 0, 0, time.UTC)
	for i := 0; i < MinConsecutiveHighFlow+3; i++ {
		tr.OnFlowWindow(context.Background(), window(start, i, 0.85, "coding"))
	}
	if api.calls < 2 {
		t.Errorf("expected the tracker to retry on error, got %d calls", api.calls)
	}
	if len(notif.calls) != 0 {
		t.Errorf("expected 0 notifications when API errors, got %d", len(notif.calls))
	}
}

func TestTracker_NotificationBodyReflectsActualMinutesNotWindowCount(t *testing.T) {
	// The previous implementation used `consecutiveHighFlow` (window
	// count) as the "minutes" value in the notification body — which
	// happened to be correct only because FlushIntervalSec defaults to
	// 60s. Reconfigure the daemon to flush every 30s and the message
	// would lie ("for 8 minutes" when only 4 minutes have actually
	// elapsed). Regression guard: 8 windows × 30s = 4 minutes.
	api := &fakeSuggester{
		response: client.AutoTimerSuggestion{ShouldSuggest: true, ProjectName: "Beats"},
	}
	notif := &notifications{}
	tr := NewTrackerWithNotifier(api, notif.record)

	start := time.Date(2026, 4, 30, 9, 0, 0, 0, time.UTC)
	for i := 0; i < MinConsecutiveHighFlow; i++ {
		// 30s windows back-to-back: window i covers [i*30, i*30+30) seconds.
		tr.OnFlowWindow(context.Background(), windowSec(start, i*30, 30, 0.85, "coding"))
	}
	if len(notif.calls) != 1 {
		t.Fatalf("expected 1 notification, got %d", len(notif.calls))
	}
	body := notif.calls[0][1]
	// 8 windows × 30s = 240s = 4 minutes. The message must say "4
	// minutes", NOT "8 minutes" (which would mean we regressed to
	// using consecutiveHighFlow as the elapsed value).
	if !strings.Contains(body, "for 4 minutes") {
		t.Errorf("expected actual elapsed minutes in body, got: %q", body)
	}
	if strings.Contains(body, "for 8 minutes") {
		t.Errorf("notification still uses window count as minutes — regression: %q", body)
	}
}
