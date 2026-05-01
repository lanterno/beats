package main

import (
	"strings"
	"testing"

	"github.com/ahmedElghable/beats/daemon/internal/client"
)

func TestParseFlowFlags_DefaultsWhenNoFlags(t *testing.T) {
	got := parseFlowFlags([]string{"recent"})
	if got.Minutes != 60 {
		t.Errorf("expected default minutes=60, got %d", got.Minutes)
	}
	if got.AsJSON {
		t.Errorf("expected --json default false, got true")
	}
	if !filterIsEmpty(got.Filter) {
		t.Errorf("expected empty filter by default, got %+v", got.Filter)
	}
}

func TestParseFlowFlags_AllFlags(t *testing.T) {
	got := parseFlowFlags([]string{
		"recent",
		"--minutes", "240",
		"--repo", "/Users/me/code/beats",
		"--language", "go",
		"--bundle", "com.microsoft.VSCode",
		"--json",
	})
	if got.Minutes != 240 {
		t.Errorf("expected minutes=240, got %d", got.Minutes)
	}
	if !got.AsJSON {
		t.Errorf("expected --json true, got false")
	}
	if got.Filter.EditorRepo != "/Users/me/code/beats" {
		t.Errorf("repo not parsed, got %q", got.Filter.EditorRepo)
	}
	if got.Filter.EditorLanguage != "go" {
		t.Errorf("language not parsed, got %q", got.Filter.EditorLanguage)
	}
	if got.Filter.BundleID != "com.microsoft.VSCode" {
		t.Errorf("bundle not parsed, got %q", got.Filter.BundleID)
	}
}

func TestParseFlowFlags_MinutesIgnoresNonPositiveAndGarbage(t *testing.T) {
	// Both 0 and "twelve" should fall back to the 60-min default rather
	// than producing a confusing tiny / zero / negative window.
	for _, bad := range []string{"0", "-5", "twelve", ""} {
		got := parseFlowFlags([]string{"recent", "--minutes", bad})
		if got.Minutes != 60 {
			t.Errorf("--minutes %q should fall back to 60, got %d", bad, got.Minutes)
		}
	}
}

func TestParseFlowFlags_UnknownFlagsAreIgnoredNotErrored(t *testing.T) {
	// Silent ignore matches what the inline dispatch arms used to do.
	// Don't break callers that pass something we add later.
	got := parseFlowFlags([]string{"recent", "--unknown", "value", "--minutes", "30"})
	if got.Minutes != 30 {
		t.Errorf("expected unknown flags to not break later parsing, got minutes=%d", got.Minutes)
	}
}

func TestParseFlowFlags_FlagWithoutValueDoesNotPanic(t *testing.T) {
	// Trailing flag with no value (e.g. `beatsd recent --repo`) — this
	// used to be a mid-iteration crash class; defensive bound check.
	got := parseFlowFlags([]string{"recent", "--repo"})
	if got.Filter.EditorRepo != "" {
		t.Errorf("trailing --repo should leave EditorRepo empty, got %q", got.Filter.EditorRepo)
	}
}

func TestParseFlowFlags_TopUseCase_OnlyMinutesMatter(t *testing.T) {
	// `top` calls parseFlowFlags but only reads .Minutes. Verify the
	// parser is well-behaved when the caller would ignore the filter
	// fields anyway — no surprise side effects.
	got := parseFlowFlags([]string{"top", "--minutes", "120"})
	if got.Minutes != 120 {
		t.Errorf("expected minutes=120, got %d", got.Minutes)
	}
	if !filterIsEmpty(got.Filter) {
		t.Errorf("expected empty filter, got %+v", got.Filter)
	}
}

func TestParseFlowFlags_HereFlag(t *testing.T) {
	// `--here` is a boolean toggle (no value follows). Parser should
	// flip Here without touching Filter.EditorRepo — resolution of
	// the actual repo path happens at dispatch time via
	// applyHereFlag, so the parser stays pure.
	got := parseFlowFlags([]string{"recent", "--here"})
	if !got.Here {
		t.Errorf("expected --here to set Here=true")
	}
	if got.Filter.EditorRepo != "" {
		t.Errorf("expected --here to leave EditorRepo empty (resolved at dispatch), got %q",
			got.Filter.EditorRepo)
	}
}

func TestApplyHereFlag_NoOpWhenHereNotSet(t *testing.T) {
	// applyHereFlag must not shell out when --here was absent — the
	// daemon shouldn't run `git rev-parse` for every `beatsd recent`
	// invocation. Returns the input untouched.
	in := flowFlags{Minutes: 30, Filter: client.FlowWindowsFilter{EditorRepo: "/explicit"}}
	out, err := applyHereFlag(in)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out.Filter.EditorRepo != "/explicit" {
		t.Errorf("expected explicit repo preserved, got %q", out.Filter.EditorRepo)
	}
}

func TestApplyHereFlag_SetsRepoFromCwd(t *testing.T) {
	// The whole point: --here resolves to a non-empty path. Tests
	// run from cmd/beatsd/, inside this repo's git tree, so the
	// resolved repo should be the project root.
	out, err := applyHereFlag(flowFlags{Here: true})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out.Filter.EditorRepo == "" {
		t.Errorf("expected --here to populate EditorRepo")
	}
}

func TestApplyHereFlag_ConflictsWithExplicitRepo(t *testing.T) {
	// --here + --repo would target the same field. We error out
	// rather than silently picking one — same rule beatsd open
	// already enforces, kept consistent across surfaces.
	_, err := applyHereFlag(flowFlags{
		Here:   true,
		Filter: client.FlowWindowsFilter{EditorRepo: "/explicit"},
	})
	if err == nil {
		t.Fatal("expected an error when --here and --repo collide")
	}
	if !strings.Contains(err.Error(), "mutually exclusive") {
		t.Errorf("expected 'mutually exclusive' in error, got: %v", err)
	}
}
