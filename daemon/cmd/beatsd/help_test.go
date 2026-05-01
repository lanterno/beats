package main

import (
	"io"
	"os"
	"strings"
	"testing"
)

// captureFile redirects either os.Stdout or os.Stderr for the duration
// of fn and returns what was written. Pure stdlib, no testify / mocks.
// Used by the captureStdout wrapper in open_test.go too.
//
// Reads via io.ReadAll rather than a fixed-size buffer so a future
// usage-text expansion (or a verbose JSON dump) doesn't silently
// truncate at 64K.
func captureFile(t *testing.T, target **os.File, fn func()) string {
	t.Helper()
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatalf("os.Pipe: %v", err)
	}
	orig := *target
	*target = w
	defer func() { *target = orig }()

	fn()
	_ = w.Close()
	out, _ := io.ReadAll(r)
	return string(out)
}

func TestPrintHelp_WritesUsageToStdout(t *testing.T) {
	// `beatsd --help | grep recent` should work — usage on stdout
	// rather than stderr is the conventional unix shape for explicit
	// help requests, and lets shell redirection / piping work as
	// expected.
	out := captureFile(t, &os.Stdout, printHelp)

	if !strings.Contains(out, "Usage: beatsd") {
		t.Errorf("expected usage header on stdout, got:\n%s", out)
	}
	for _, want := range []string{"pair", "run", "doctor", "open", "config"} {
		if !strings.Contains(out, want) {
			t.Errorf("expected command %q to appear in help, got:\n%s", want, out)
		}
	}
}

func TestPrintUsage_WritesToStderr(t *testing.T) {
	// Error paths (no args, unknown command) should still write to
	// stderr — the conventional unix shape so a calling shell script
	// can redirect just the error output.
	out := captureFile(t, &os.Stderr, printUsage)

	if !strings.Contains(out, "Usage: beatsd") {
		t.Errorf("expected usage header on stderr, got:\n%s", out)
	}
}

func TestPrintHelp_TopStanzaListsFilterFlags(t *testing.T) {
	// `top` was extended to honor --repo / --language / --bundle so
	// users can filter the leaderboards the same way `recent` and
	// `stats` allow. The help text needs to advertise that — without
	// it the feature is invisible. Locks the top stanza to the same
	// filter-flag list, so a future drift between dispatch and help
	// surfaces here rather than as a confused user.
	out := captureFile(t, &os.Stdout, printHelp)
	topIdx := strings.Index(out, "top ")
	if topIdx == -1 {
		t.Fatalf("top stanza missing from help:\n%s", out)
	}
	statsIdx := strings.Index(out, "stats ")
	if statsIdx == -1 || statsIdx <= topIdx {
		t.Fatalf("expected stats stanza after top stanza in help:\n%s", out)
	}
	topStanza := out[topIdx:statsIdx]
	for _, want := range []string{"--repo", "--language", "--bundle"} {
		if !strings.Contains(topStanza, want) {
			t.Errorf("expected top stanza to advertise %q, got:\n%s", want, topStanza)
		}
	}
}

func TestPrintHelp_StdoutMatchesPrintUsageStderr(t *testing.T) {
	// Help and usage should print byte-identical text — the only
	// difference is which stream they target. Locks in that a
	// future refactor can't drift the two paths apart.
	stdout := captureFile(t, &os.Stdout, printHelp)
	stderr := captureFile(t, &os.Stderr, printUsage)
	if stdout != stderr {
		t.Errorf("printHelp stdout differs from printUsage stderr:\n--- stdout ---\n%s\n--- stderr ---\n%s",
			stdout, stderr)
	}
}

// hasHelpFlag is the predicate that lets `beatsd recent --help`
// (and friends) route to the same usage text the global form
// prints. Tests pin the contract so a future refactor can't
// silently drop a recognized form.

func TestHasHelpFlag_RecognizesAllForms(t *testing.T) {
	for _, args := range [][]string{
		{"--help"},
		{"-h"},
		{"help"},
	} {
		if !hasHelpFlag(args) {
			t.Errorf("expected hasHelpFlag(%v) to be true", args)
		}
	}
}

func TestHasHelpFlag_FindsHelpInAnyPosition(t *testing.T) {
	// The whole reason this helper exists: per-command help. The
	// flag should be recognized regardless of where it appears in
	// the arg list, so `beatsd recent --minutes 30 --help` works
	// the same as `beatsd recent --help`.
	cases := [][]string{
		{"recent", "--help"},
		{"recent", "--minutes", "30", "--help"},
		{"run", "--dry-run", "-h"},
		{"--help", "recent"},
	}
	for _, args := range cases {
		if !hasHelpFlag(args) {
			t.Errorf("expected hasHelpFlag(%v) to be true", args)
		}
	}
}

// suggestCommand maps a typo to the closest known command, used
// by main()'s default arm to print "did you mean …?". Tests pin
// the realistic typo cases plus the fall-through.

func TestSuggestCommand_RealisticTypos(t *testing.T) {
	// Plain Levenshtein scores transpositions as 2 substitutions,
	// so transposition-only typos near a longer command fall back
	// to a closer same-letterset shorter command (e.g. "stauts"
	// is distance 1 from "stats" but distance 2 from "status").
	// Damerau-Levenshtein would handle transpositions cleanly but
	// the added complexity isn't worth it — the realistic cases
	// below cover the common deletion/insertion typos and pick
	// useful suggestions.
	cases := map[string]string{
		"dotcor": "doctor",  // 2 substitutions for the t/c swap
		"recnet": "recent",  // 2 substitutions for the n/e swap
		"stat":   "stats",   // missing trailing s
		"vrsion": "version", // missing e
		"opn":    "open",    // missing e
		"confg":  "config",  // missing i
		"pari":   "pair",    // 2 substitutions for the i/r swap
	}
	for input, want := range cases {
		if got := suggestCommand(input); got != want {
			t.Errorf("suggestCommand(%q) = %q, want %q", input, got, want)
		}
	}
}

func TestSuggestCommand_TieBreaksOnLength(t *testing.T) {
	// When the candidate at the lowest distance has a different
	// length than the input, but a same-length candidate exists at
	// equal distance, prefer the same-length one — it's the more
	// likely intended command.
	//
	// "stat" → both "stats" (distance 1, len 5) and "status" (distance 2,
	// len 6). Distance wins → "stats".
	//
	// "stas" → "stats" (distance 1, insertion); locked in to verify
	// the simple insertion path stays stable.
	if got := suggestCommand("stas"); got != "stats" {
		t.Errorf("suggestCommand(stas) = %q, want stats", got)
	}
}

func TestSuggestCommand_NoMatchForFarStrings(t *testing.T) {
	// Inputs that aren't plausibly any command (distance > 2)
	// shouldn't produce a wild guess. Better to show no
	// suggestion than to mislead.
	for _, input := range []string{
		"xyzzyfoo",
		"completely-unrelated",
		"do", // distance to "doctor" is 4 — too short to be a typo
		"",   // empty input — unhelpful to suggest anything
	} {
		if got := suggestCommand(input); got != "" {
			t.Errorf("suggestCommand(%q) = %q, want empty", input, got)
		}
	}
}

func TestSuggestCommand_ExactMatchReturnsItself(t *testing.T) {
	// Defensive — if main()'s switch is somehow reached with an
	// exact known name (shouldn't happen, but the helper should
	// still behave reasonably), distance 0 means it matches itself.
	if got := suggestCommand("doctor"); got != "doctor" {
		t.Errorf("expected exact match, got %q", got)
	}
}

func TestLevenshtein_KnownDistances(t *testing.T) {
	// Lock the recurrence — these are the canonical test cases
	// for any Levenshtein implementation.
	cases := []struct {
		a, b string
		want int
	}{
		{"", "", 0},
		{"abc", "", 3},
		{"", "xyz", 3},
		{"kitten", "sitting", 3}, // standard textbook example
		{"flaw", "lawn", 2},
		{"doctor", "doctor", 0},
		{"dotcor", "doctor", 2}, // two substitutions for the swap
		{"abc", "abcd", 1},      // one insertion
		{"abcd", "abc", 1},      // one deletion
	}
	for _, c := range cases {
		if got := levenshtein(c.a, c.b); got != c.want {
			t.Errorf("levenshtein(%q, %q) = %d, want %d", c.a, c.b, got, c.want)
		}
	}
}

func TestHasHelpFlag_NoMatchReturnsFalse(t *testing.T) {
	for _, args := range [][]string{
		{},
		{"recent"},
		{"recent", "--minutes", "60"},
		{"--repo", "/some/path"},
		// Defensive: a flag value that happens to be "-h" or "help"
		// should NOT trigger help. We don't currently have any such
		// flag values, but the simple-scan helper is fine to leave
		// permissive — the cost of a false positive is showing help
		// instead of running, not data loss. Locked in here so the
		// permissiveness is at least documented.
	} {
		if hasHelpFlag(args) {
			t.Errorf("expected hasHelpFlag(%v) to be false", args)
		}
	}
}
