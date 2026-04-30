package main

import (
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
	out := formatTop(windows, 60)

	for _, want := range []string{"BY REPO", "BY LANGUAGE", "BY APP", "code/beats", "go", "coding"} {
		if !strings.Contains(out, want) {
			t.Errorf("expected output to contain %q, got:\n%s", want, out)
		}
	}
}

func TestFormatTop_EmptyShowsHelpfulHint(t *testing.T) {
	out := formatTop(nil, 60)
	if !strings.Contains(out, "no flow windows") {
		t.Errorf("expected helpful empty-state hint, got: %s", out)
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
	out := formatTop(windows, 60)

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
