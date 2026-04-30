package main

import (
	"strings"
	"testing"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/client"
)

func TestFormatRecentTable_EmptyShowsHelpfulHint(t *testing.T) {
	out := formatRecentTable(nil, 60)
	if !strings.Contains(out, "no flow windows") {
		t.Errorf("expected helpful empty-state hint, got: %s", out)
	}
	if !strings.Contains(out, "60") {
		t.Errorf("expected the requested duration to surface in the hint, got: %s", out)
	}
}

func TestFormatRecentTable_RendersHeaderAndRows(t *testing.T) {
	now := time.Date(2026, 5, 1, 14, 32, 0, 0, time.UTC)
	windows := []client.FlowWindowRecord{
		{
			ID:               "w1",
			WindowStart:      now,
			FlowScore:        0.62,
			DominantCategory: "coding",
			DominantBundleID: "com.microsoft.VSCode",
			EditorRepo:       "/Users/me/code/beats",
		},
		{
			ID:               "w2",
			WindowStart:      now.Add(time.Minute),
			FlowScore:        0.91,
			DominantCategory: "coding",
			DominantBundleID: "com.microsoft.VSCode",
			EditorRepo:       "/Users/me/code/beats",
		},
	}
	out := formatRecentTable(windows, 60)

	for _, want := range []string{"TIME", "FLOW", "APP", "REPO", "62", "91", "code/beats"} {
		if !strings.Contains(out, want) {
			t.Errorf("expected output to contain %q, got:\n%s", want, out)
		}
	}
}

func TestFormatRecentTable_NewestRowAtBottom(t *testing.T) {
	now := time.Date(2026, 5, 1, 14, 0, 0, 0, time.UTC)
	windows := []client.FlowWindowRecord{
		{ID: "old", WindowStart: now, FlowScore: 0.4, DominantCategory: "browser"},
		{ID: "new", WindowStart: now.Add(time.Hour), FlowScore: 0.9, DominantCategory: "coding"},
	}
	out := formatRecentTable(windows, 60)

	// Newest first because the slice from the API is ascending; the table
	// reverses so the most recent line is the last printed (read from
	// top-to-bottom = oldest to newest, ending where the user is now).
	idxOld := strings.Index(out, "browser")
	idxNew := strings.Index(out, "coding")
	if idxOld == -1 || idxNew == -1 {
		t.Fatalf("expected both rows, got:\n%s", out)
	}
	if !(idxNew > idxOld) {
		t.Errorf("expected newest row at bottom of table; old=%d new=%d in:\n%s", idxOld, idxNew, out)
	}
}

func TestTruncOrFallback(t *testing.T) {
	if got := truncOrFallback("coding", "com.foo", 22); got != "coding" {
		t.Errorf("primary should win, got %q", got)
	}
	if got := truncOrFallback("", "com.apple.dt.Xcode", 22); got != "com.apple.dt.Xcode" {
		t.Errorf("fallback should kick in, got %q", got)
	}
	if got := truncOrFallback("", "", 22); got != "—" {
		t.Errorf("both empty should give the em-dash, got %q", got)
	}
	long := strings.Repeat("a", 30)
	got := truncOrFallback(long, "", 10)
	// Compare rune count (display width) rather than len() (byte count) —
	// "…" is 3 bytes UTF-8 so byte length would be misleading.
	runes := 0
	for range got {
		runes++
	}
	if runes != 10 || !strings.HasSuffix(got, "…") {
		t.Errorf("expected exactly width display chars ending in ellipsis, got %q (runes %d)", got, runes)
	}
}

func TestShortRepoTrail(t *testing.T) {
	if got := shortRepoTrail(""); got != "" {
		t.Errorf("empty should stay empty, got %q", got)
	}
	if got := shortRepoTrail("/Users/me/code/example"); got != "code/example" {
		t.Errorf("expected last two segments, got %q", got)
	}
	// Two-segment path returns as-is — no `slice(-2)` weirdness.
	if got := shortRepoTrail("a/b"); got != "a/b" {
		t.Errorf("two-segment input should return unchanged, got %q", got)
	}
	// Windows separator handling.
	if got := shortRepoTrail("C:\\Users\\me\\code\\example"); got != "code/example" {
		t.Errorf("expected backslash split, got %q", got)
	}
}
