package main

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/client"
)

func TestAggregateBy_GroupsAndOrders(t *testing.T) {
	now := time.Date(2026, 5, 1, 14, 0, 0, 0, time.UTC)
	windows := []client.FlowWindowRecord{
		{WindowStart: now, FlowScore: 0.9, EditorLanguage: "go"},
		{WindowStart: now.Add(time.Minute), FlowScore: 0.8, EditorLanguage: "go"},
		{WindowStart: now.Add(2 * time.Minute), FlowScore: 0.5, EditorLanguage: "typescript"},
	}
	got := aggregateBy(windows, func(w client.FlowWindowRecord) string {
		return w.EditorLanguage
	})

	if len(got) != 2 {
		t.Fatalf("expected 2 buckets, got %d", len(got))
	}
	// "go" should win on count (2 vs 1) and land first.
	if got[0].Key != "go" || got[0].Count != 2 {
		t.Errorf("expected go bucket first with count=2, got %+v", got[0])
	}
	// avg of 0.9 and 0.8 is 0.85 — verify the unweighted mean (within
	// floating-point tolerance — 0.9+0.8=1.7 isn't exactly representable).
	if diff := got[0].Avg - 0.85; diff > 1e-9 || diff < -1e-9 {
		t.Errorf("expected avg ≈ 0.85, got %v", got[0].Avg)
	}
}

func TestAggregateBy_SkipsEmptyKeys(t *testing.T) {
	// Windows with no editor heartbeat (empty EditorLanguage) shouldn't
	// collapse into an "(unknown)" bucket — that would just be noise on
	// the leaderboard.
	windows := []client.FlowWindowRecord{
		{FlowScore: 0.9, EditorLanguage: ""},
		{FlowScore: 0.8, EditorLanguage: ""},
		{FlowScore: 0.7, EditorLanguage: "go"},
	}
	got := aggregateBy(windows, func(w client.FlowWindowRecord) string {
		return w.EditorLanguage
	})

	if len(got) != 1 || got[0].Key != "go" {
		t.Errorf("expected only the 'go' bucket, got %+v", got)
	}
}

func TestAggregateBy_TieBreaksOnAvgScore(t *testing.T) {
	// Two languages tied at count=1; the higher-avg one should rank first
	// so the user sees the higher-quality bucket when minutes match.
	windows := []client.FlowWindowRecord{
		{FlowScore: 0.5, EditorLanguage: "rust"},
		{FlowScore: 0.9, EditorLanguage: "go"},
	}
	got := aggregateBy(windows, func(w client.FlowWindowRecord) string {
		return w.EditorLanguage
	})

	if got[0].Key != "go" {
		t.Errorf("expected 'go' first on tied count + higher avg, got %+v", got)
	}
}

func TestAggregateBy_CapsAtFive(t *testing.T) {
	// Six distinct buckets; the helper should return only the top 5.
	var windows []client.FlowWindowRecord
	for _, lang := range []string{"a", "b", "c", "d", "e", "f"} {
		windows = append(windows, client.FlowWindowRecord{FlowScore: 0.5, EditorLanguage: lang})
	}
	got := aggregateBy(windows, func(w client.FlowWindowRecord) string {
		return w.EditorLanguage
	})

	if len(got) != 5 {
		t.Errorf("expected leaderboard capped at 5 rows, got %d", len(got))
	}
}

func TestFormatTop_RendersAllThreeSections(t *testing.T) {
	now := time.Date(2026, 5, 1, 14, 0, 0, 0, time.UTC)
	windows := []client.FlowWindowRecord{
		{
			WindowStart:      now,
			FlowScore:        0.91,
			DominantCategory: "coding",
			DominantBundleID: "com.microsoft.VSCode",
			EditorRepo:       "/Users/me/code/beats",
			EditorLanguage:   "go",
		},
	}
	out := formatTop(windows, 60, client.FlowWindowsFilter{})

	for _, want := range []string{"BY REPO", "BY LANGUAGE", "BY APP", "code/beats", "go", "coding"} {
		if !strings.Contains(out, want) {
			t.Errorf("expected output to contain %q, got:\n%s", want, out)
		}
	}
}

func TestFormatTop_EmptyShowsHelpfulHint(t *testing.T) {
	out := formatTop(nil, 60, client.FlowWindowsFilter{})
	if !strings.Contains(out, "no flow windows") {
		t.Errorf("expected helpful empty-state hint, got: %s", out)
	}
	if !strings.Contains(out, "beatsd run") {
		t.Errorf("unfiltered empty state should suggest checking the daemon, got: %s", out)
	}
}

func TestFormatTop_EmptyWithFilterBlamesFilter(t *testing.T) {
	// Same context-aware hint stats/recent use — when the user has
	// narrowed the slice to nothing, point at the filter rather than
	// the daemon process.
	out := formatTop(nil, 60, client.FlowWindowsFilter{EditorLanguage: "rust"})
	if !strings.Contains(out, "filter") {
		t.Errorf("filtered empty should mention the filter, got: %s", out)
	}
	if strings.Contains(out, "beatsd run") {
		t.Errorf("filtered empty should NOT blame the daemon, got: %s", out)
	}
}

func TestFormatTop_FilterCaptionAppendedToHeader(t *testing.T) {
	// When a filter is active, the caption (e.g. "lang=go") should land
	// in the header so the user can tell which slice the leaderboards
	// represent — mirrors the recent/stats behavior.
	now := time.Date(2026, 5, 1, 14, 0, 0, 0, time.UTC)
	windows := []client.FlowWindowRecord{
		{
			WindowStart: now, FlowScore: 0.9,
			EditorRepo: "/Users/me/code/beats", EditorLanguage: "go",
		},
	}
	out := formatTop(windows, 60, client.FlowWindowsFilter{EditorLanguage: "go"})
	if !strings.Contains(out, "lang=go") {
		t.Errorf("expected filter caption in header, got:\n%s", out)
	}
}

func TestFormatTop_LeaderboardWithNoEntriesShowsDash(t *testing.T) {
	// Windows present but none carry editor context. The "BY REPO" and
	// "BY LANGUAGE" sections should each render a "—" placeholder so the
	// header doesn't visually swallow itself, while "BY APP" still has
	// real rows from the dominant_category fallback.
	windows := []client.FlowWindowRecord{
		{FlowScore: 0.5, DominantCategory: "browser"},
	}
	out := formatTop(windows, 60, client.FlowWindowsFilter{})

	// Find each header and confirm structure under it.
	repoIdx := strings.Index(out, "BY REPO")
	langIdx := strings.Index(out, "BY LANGUAGE")
	appIdx := strings.Index(out, "BY APP")
	if repoIdx == -1 || langIdx == -1 || appIdx == -1 {
		t.Fatalf("missing one of the three headers in:\n%s", out)
	}
	// Between BY REPO and BY LANGUAGE there should be the placeholder dash.
	repoSection := out[repoIdx:langIdx]
	if !strings.Contains(repoSection, "—") {
		t.Errorf("expected placeholder dash under empty BY REPO, got:\n%s", repoSection)
	}
}

func TestFormatTopJSON_RoundTripsAndAlwaysHasAllThreeAxes(t *testing.T) {
	// JSON output must parse back into the documented topJSONOutput
	// shape and always include all three axis keys (each may be []) so
	// jq scripts don't need to guard against missing keys.
	now := time.Date(2026, 5, 1, 14, 0, 0, 0, time.UTC)
	windows := []client.FlowWindowRecord{
		{
			WindowStart:      now,
			FlowScore:        0.9,
			DominantBundleID: "com.microsoft.VSCode",
			DominantCategory: "coding",
			EditorRepo:       "/Users/me/code/beats",
			EditorLanguage:   "go",
		},
		{
			WindowStart:      now.Add(time.Minute),
			FlowScore:        0.8,
			DominantBundleID: "com.microsoft.VSCode",
			DominantCategory: "coding",
			EditorRepo:       "/Users/me/code/beats",
			EditorLanguage:   "go",
		},
	}
	out, err := formatTopJSON(windows)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.HasSuffix(out, "\n") {
		t.Errorf("expected trailing newline so shell prompt lands cleanly, got %q", out)
	}

	var decoded topJSONOutput
	if err := json.Unmarshal([]byte(out), &decoded); err != nil {
		t.Fatalf("output should round-trip through json.Unmarshal: %v\noutput: %s", err, out)
	}
	if len(decoded.ByRepo) != 1 || decoded.ByRepo[0].Key != "/Users/me/code/beats" {
		t.Errorf("by_repo wrong, got %+v", decoded.ByRepo)
	}
	if len(decoded.ByLanguage) != 1 || decoded.ByLanguage[0].Key != "go" {
		t.Errorf("by_language wrong, got %+v", decoded.ByLanguage)
	}
	if len(decoded.ByApp) != 1 || decoded.ByApp[0].Key != "com.microsoft.VSCode" {
		t.Errorf("by_app should use the raw bundle id (not the 'coding' category label), got %+v", decoded.ByApp)
	}
}

func TestFormatTopJSON_EmptyAxesAreArraysNotNull(t *testing.T) {
	// Windows present but with no editor heartbeats — by_repo and
	// by_language should be `[]`, not omitted or null. by_app falls
	// back to dominant_category when bundle_id is empty.
	windows := []client.FlowWindowRecord{
		{FlowScore: 0.5, DominantCategory: "browser"},
	}
	out, err := formatTopJSON(windows)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if !strings.Contains(out, `"by_repo": []`) {
		t.Errorf("expected by_repo to be an empty JSON array, got: %s", out)
	}
	if !strings.Contains(out, `"by_language": []`) {
		t.Errorf("expected by_language to be an empty JSON array, got: %s", out)
	}
	// by_app should fall back to the category label since no bundle id
	// was set on the input window.
	if !strings.Contains(out, `"key": "browser"`) {
		t.Errorf("expected by_app to use the category fallback, got: %s", out)
	}
}

func TestFormatTopJSON_NoWindowsStillReturnsValidObject(t *testing.T) {
	// jq users shouldn't have to special-case "no flow today" — empty
	// input returns the same shape with empty arrays.
	out, err := formatTopJSON(nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	var decoded topJSONOutput
	if err := json.Unmarshal([]byte(out), &decoded); err != nil {
		t.Fatalf("empty output should still parse: %v", err)
	}
	if decoded.ByRepo == nil || decoded.ByLanguage == nil || decoded.ByApp == nil {
		t.Errorf("empty axes should be [], not nil — got %+v", decoded)
	}
	if len(decoded.ByRepo) != 0 || len(decoded.ByLanguage) != 0 || len(decoded.ByApp) != 0 {
		t.Errorf("expected empty arrays, got %+v", decoded)
	}
}
