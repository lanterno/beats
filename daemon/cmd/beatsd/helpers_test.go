package main

import "testing"

// Pure-helper tests for the small string utilities scattered across
// main.go and status.go. Each is called from a production path
// (dry-run log line, status table) and was at 0% coverage — easy to
// regress silently in a refactor without these tests pinning the
// contract.

// --- shortRepo (main.go) ---

// shortRepo is the basename-only helper used by the dry-run log
// line, distinct from `shortRepoTrail` which keeps the last two
// segments for the recent/stats tables. Different output for the
// same input is intentional: log lines want one short word; tables
// need enough context to disambiguate two repos with the same
// basename.

func TestShortRepo_ReturnsBasename(t *testing.T) {
	if got := shortRepo("/Users/me/code/beats"); got != "beats" {
		t.Errorf("expected basename, got %q", got)
	}
}

func TestShortRepo_HandlesWindowsSeparator(t *testing.T) {
	if got := shortRepo(`C:\Users\me\code\beats`); got != "beats" {
		t.Errorf("expected basename across \\, got %q", got)
	}
}

func TestShortRepo_NoSlashReturnsAsIs(t *testing.T) {
	// A single-segment input (rare but possible — relative path,
	// editor that doesn't resolve to absolute) should return
	// unchanged rather than empty.
	if got := shortRepo("beats"); got != "beats" {
		t.Errorf("expected unchanged single-segment, got %q", got)
	}
}

func TestShortRepo_EmptyReturnsDash(t *testing.T) {
	// Log lines need SOMETHING to render in the repo slot when no
	// editor heartbeat covered the window — `-` reads as "absent"
	// without making the line look like a malformed key=value pair.
	if got := shortRepo(""); got != "-" {
		t.Errorf("expected dash for empty, got %q", got)
	}
}

func TestShortRepo_TrailingSlashReturnsWholePath(t *testing.T) {
	// Edge case the lastSlash predicate guards against: if the path
	// ends in /, the basename slice would be empty. Falling back to
	// the whole input is the least-surprising behavior.
	if got := shortRepo("/Users/me/code/beats/"); got != "/Users/me/code/beats/" {
		t.Errorf("expected whole-path fallback for trailing slash, got %q", got)
	}
}

// --- lastSlash (main.go) ---

func TestLastSlash_FindsForwardSlash(t *testing.T) {
	if got := lastSlash("/Users/me/code/beats"); got != 14 {
		t.Errorf("expected 14, got %d", got)
	}
}

func TestLastSlash_FindsBackslash(t *testing.T) {
	// Cross-platform: a Windows path uses backslash. The helper
	// treats either as a separator so shortRepo produces the same
	// basename across OSes.
	if got := lastSlash(`C:\Users\me`); got != 8 {
		t.Errorf("expected 8, got %d", got)
	}
}

func TestLastSlash_PrefersLatest(t *testing.T) {
	// Mixed separators (rare — a copy/pasted path on Windows under
	// Cygwin or WSL) should still resolve to the rightmost. Locks
	// in the loop's right-to-left scan rule.
	if got := lastSlash("a/b\\c"); got != 3 {
		t.Errorf("expected 3 (the trailing backslash), got %d", got)
	}
}

func TestLastSlash_NoSeparatorReturnsMinusOne(t *testing.T) {
	if got := lastSlash("beats"); got != -1 {
		t.Errorf("expected -1, got %d", got)
	}
}

func TestLastSlash_EmptyReturnsMinusOne(t *testing.T) {
	if got := lastSlash(""); got != -1 {
		t.Errorf("expected -1 for empty, got %d", got)
	}
}

// --- truncate (status.go) ---

// truncate is used by `beatsd status` to keep MongoDB ObjectId
// project ids (24 chars) readable without losing disambiguation.
// At width 12, a typical ObjectId becomes "507f1f77bcf…".

func TestTruncate_ShortStringPassesThrough(t *testing.T) {
	if got := truncate("abc", 10); got != "abc" {
		t.Errorf("expected unchanged when short enough, got %q", got)
	}
}

func TestTruncate_ExactWidthPassesThrough(t *testing.T) {
	// Fence-post: at exactly the limit we should NOT add the
	// ellipsis. Adding one would make the output longer than the
	// limit, defeating the purpose.
	in := "0123456789"
	if got := truncate(in, 10); got != in {
		t.Errorf("expected unchanged at exact width, got %q", got)
	}
}

func TestTruncate_OverflowGetsEllipsis(t *testing.T) {
	// truncate's contract is "at most n input chars + ellipsis
	// indicator on overflow" — distinct from recent.go's
	// truncOrFallback which keeps the total visual width at
	// exactly `width`. Here `n` is the cap on the input slice,
	// not the rendered total. The status line has no fixed-width
	// budget so the ellipsis-as-overflow-cue cost is fine.
	got := truncate("507f1f77bcf86cd799439011", 12)
	if got != "507f1f77bcf8…" {
		t.Errorf("expected first 12 chars + ellipsis, got %q", got)
	}
}

func TestTruncate_ZeroWidthReturnsEmpty(t *testing.T) {
	// Defensive: caller passing 0 (e.g. a config line that defaults
	// to 0 and was never set) shouldn't crash — return empty rather
	// than panic on a negative slice.
	if got := truncate("anything", 0); got != "" {
		t.Errorf("expected empty for n=0, got %q", got)
	}
}

func TestTruncate_NegativeWidthReturnsEmpty(t *testing.T) {
	// Same defensive contract as the n=0 case.
	if got := truncate("anything", -5); got != "" {
		t.Errorf("expected empty for negative n, got %q", got)
	}
}

func TestTruncate_EmptyInputReturnsEmpty(t *testing.T) {
	if got := truncate("", 10); got != "" {
		t.Errorf("expected empty in/out, got %q", got)
	}
}
