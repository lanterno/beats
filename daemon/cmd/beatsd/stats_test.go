package main

import (
	"strings"
	"testing"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/client"
)

func TestFormatStatsLine_HappyPath(t *testing.T) {
	peakAt := time.Date(2026, 5, 1, 14, 32, 0, 0, time.UTC)
	s := &client.FlowWindowSummary{
		Count:   23,
		Avg:     0.67,
		Peak:    0.91,
		PeakAt:  &peakAt,
		TopRepo: &client.FlowTopItem{Key: "/Users/me/code/beats", Avg: 0.74, Count: 18},
	}
	out := formatStatsLine(s, 60, client.FlowWindowsFilter{})

	for _, want := range []string{
		"last 60 min",
		"23 windows",
		"avg 67",
		"peak 91 at",
		"best repo: code/beats",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("expected stats line to contain %q, got: %s", want, out)
		}
	}
}

func TestFormatStatsLine_FilterCaptionAppended(t *testing.T) {
	// When a filter is active, the caption from filterCaption() should
	// land at the end so the user can see what slice the headline
	// represents.
	peakAt := time.Now().UTC()
	s := &client.FlowWindowSummary{
		Count: 5, Avg: 0.5, Peak: 0.7, PeakAt: &peakAt,
	}
	out := formatStatsLine(s, 60, client.FlowWindowsFilter{EditorLanguage: "go"})
	if !strings.Contains(out, "lang=go") {
		t.Errorf("expected filter caption to surface, got: %s", out)
	}
}

func TestFormatStatsLine_EmptyShowsHelpfulHint(t *testing.T) {
	out := formatStatsLine(&client.FlowWindowSummary{Count: 0}, 60, client.FlowWindowsFilter{})
	if !strings.Contains(out, "no flow windows") {
		t.Errorf("expected empty-state hint, got: %s", out)
	}
	if !strings.Contains(out, "beatsd run") {
		t.Errorf("unfiltered empty state should suggest checking the daemon, got: %s", out)
	}
}

func TestFormatStatsLine_EmptyWithFilterBlamesFilter(t *testing.T) {
	// Same context-aware hint as the recent table — when the user has
	// filtered down to nothing, point at the filter rather than the
	// daemon process.
	out := formatStatsLine(
		&client.FlowWindowSummary{Count: 0},
		60,
		client.FlowWindowsFilter{EditorRepo: "/path/that/has/no/data"},
	)
	if !strings.Contains(out, "filter") {
		t.Errorf("filtered empty should mention the filter, got: %s", out)
	}
	if strings.Contains(out, "beatsd run") {
		t.Errorf("filtered empty should NOT blame the daemon, got: %s", out)
	}
}

func TestFormatStatsLine_NilSummaryHandledGracefully(t *testing.T) {
	// Defensive: a nil summary (network glitch or 204) should not panic
	// and should print the same empty-state hint.
	out := formatStatsLine(nil, 60, client.FlowWindowsFilter{})
	if !strings.Contains(out, "no flow windows") {
		t.Errorf("expected empty-state hint for nil summary, got: %s", out)
	}
}

func TestFormatStatsLine_OmitsBestRepoWhenAxisEmpty(t *testing.T) {
	// When no editor heartbeats covered the slice, TopRepo is nil — the
	// stats line should skip that chunk rather than render "best repo:"
	// with no value.
	peakAt := time.Now().UTC()
	s := &client.FlowWindowSummary{
		Count: 5, Avg: 0.5, Peak: 0.7, PeakAt: &peakAt,
	}
	out := formatStatsLine(s, 60, client.FlowWindowsFilter{})
	if strings.Contains(out, "best repo") {
		t.Errorf("expected best-repo chunk to be omitted, got: %s", out)
	}
}
