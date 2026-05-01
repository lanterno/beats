package main

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/client"
)

func TestFormatRecentTable_EmptyShowsHelpfulHint(t *testing.T) {
	out := formatRecentTable(nil, 60, client.FlowWindowsFilter{})
	if !strings.Contains(out, "no flow windows") {
		t.Errorf("expected helpful empty-state hint, got: %s", out)
	}
	if !strings.Contains(out, "60") {
		t.Errorf("expected the requested duration to surface in the hint, got: %s", out)
	}
	if !strings.Contains(out, "beatsd run") {
		t.Errorf("unfiltered empty state should suggest checking the daemon, got: %s", out)
	}
}

func TestFormatRecentTable_EmptyWithFilterBlamesFilter(t *testing.T) {
	// When the user has narrowed and the result is empty, the hint should
	// point at the filter rather than the daemon — otherwise we send them
	// chasing a non-existent process problem.
	out := formatRecentTable(nil, 60, client.FlowWindowsFilter{EditorLanguage: "rust"})
	if !strings.Contains(out, "filter") {
		t.Errorf("filtered empty state should mention the filter, got: %s", out)
	}
	if strings.Contains(out, "beatsd run") {
		t.Errorf("filtered empty state should NOT suggest the daemon is down, got: %s", out)
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
	out := formatRecentTable(windows, 60, client.FlowWindowsFilter{})

	for _, want := range []string{"TIME", "FLOW", "APP", "REPO", "62", "91", "code/beats"} {
		if !strings.Contains(out, want) {
			t.Errorf("expected output to contain %q, got:\n%s", want, out)
		}
	}
}

func TestFormatRecentTable_RendersFriendlyAppNameWhenCategoryEmpty(t *testing.T) {
	// When the daemon hasn't classified the frontmost app into a
	// category (e.g. an unknown bundle), the table used to render the
	// raw "com.microsoft.VSCode" — ugly. Now it routes through
	// bundle.ShortLabel so the user sees "VS Code" instead. Same
	// friendly-label set the web FlowHeadline + companion FlowScreen
	// + `beatsd stats` use.
	now := time.Date(2026, 5, 1, 14, 32, 0, 0, time.UTC)
	windows := []client.FlowWindowRecord{
		{
			WindowStart:      now,
			FlowScore:        0.7,
			DominantCategory: "", // category empty → fallback to bundle
			DominantBundleID: "com.microsoft.VSCode",
		},
	}
	out := formatRecentTable(windows, 60, client.FlowWindowsFilter{})

	if !strings.Contains(out, "VS Code") {
		t.Errorf("expected friendly app label, got:\n%s", out)
	}
	if strings.Contains(out, "com.microsoft.VSCode") {
		t.Errorf("expected raw bundle id to be replaced, got:\n%s", out)
	}
}

func TestFormatRecentTable_FilterCaptionInHeader(t *testing.T) {
	// When a filter is active, the header line should announce it so the
	// user can tell at a glance which slice the table represents.
	now := time.Date(2026, 5, 1, 14, 32, 0, 0, time.UTC)
	windows := []client.FlowWindowRecord{
		{ID: "w1", WindowStart: now, FlowScore: 0.62, EditorRepo: "/Users/me/code/beats"},
	}
	filter := client.FlowWindowsFilter{
		EditorRepo:     "/Users/me/code/beats",
		EditorLanguage: "go",
		BundleID:       "com.microsoft.VSCode",
	}
	out := formatRecentTable(windows, 60, filter)

	for _, want := range []string{"repo=code/beats", "lang=go", "app=com.microsoft.VSCode"} {
		if !strings.Contains(out, want) {
			t.Errorf("expected caption to contain %q, got:\n%s", want, out)
		}
	}
}

func TestFormatRecentTable_NewestRowAtBottom(t *testing.T) {
	now := time.Date(2026, 5, 1, 14, 0, 0, 0, time.UTC)
	windows := []client.FlowWindowRecord{
		{ID: "old", WindowStart: now, FlowScore: 0.4, DominantCategory: "browser"},
		{ID: "new", WindowStart: now.Add(time.Hour), FlowScore: 0.9, DominantCategory: "coding"},
	}
	out := formatRecentTable(windows, 60, client.FlowWindowsFilter{})

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

func TestFormatRecentJSON_RoundTrips(t *testing.T) {
	// JSON output must parse back into the same slice — that's the whole
	// point of the format ("beatsd recent --json | jq" should work).
	now := time.Date(2026, 5, 1, 14, 0, 0, 0, time.UTC)
	windows := []client.FlowWindowRecord{
		{
			ID:               "w1",
			WindowStart:      now,
			WindowEnd:        now.Add(time.Minute),
			FlowScore:        0.74,
			DominantBundleID: "com.microsoft.VSCode",
			EditorRepo:       "/Users/me/code/beats",
			EditorLanguage:   "go",
		},
	}
	out, err := formatRecentJSON(windows)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.HasSuffix(out, "\n") {
		t.Errorf("expected trailing newline so shell prompt lands cleanly, got %q", out)
	}

	var decoded []client.FlowWindowRecord
	if err := json.Unmarshal([]byte(out), &decoded); err != nil {
		t.Fatalf("output should round-trip through json.Unmarshal: %v\noutput: %s", err, out)
	}
	if len(decoded) != 1 || decoded[0].ID != "w1" || decoded[0].EditorLanguage != "go" {
		t.Errorf("round-trip lost data, got: %+v", decoded)
	}
}

func TestFormatRecentJSON_EmptyIsArrayNotNull(t *testing.T) {
	// When there are no rows we still emit `[]` — `jq` users would have
	// to special-case `null` otherwise. Pipe-friendly trumps shorter.
	out, err := formatRecentJSON(nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(out, "[]") || strings.Contains(out, "null") {
		t.Errorf("expected an empty JSON array, got: %q", out)
	}

	var decoded []client.FlowWindowRecord
	if err := json.Unmarshal([]byte(out), &decoded); err != nil {
		t.Fatalf("empty output should still parse as an array: %v", err)
	}
	if len(decoded) != 0 {
		t.Errorf("decoded length should be 0, got %d", len(decoded))
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
