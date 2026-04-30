package notify

import "testing"

// psEscape doubles single quotes for safe inclusion in a PowerShell
// single-quoted string. Other characters pass through unchanged. Pinning
// the contract here so a future refactor (e.g. switching to a
// $-prefixed PowerShell string) can't accidentally drop legitimate
// characters or fail to escape something that matters.

func TestPsEscape_Empty(t *testing.T) {
	if got := psEscape(""); got != "" {
		t.Errorf("expected empty in/out, got %q", got)
	}
}

func TestPsEscape_NoQuotesPassesThrough(t *testing.T) {
	cases := []string{
		"plain text",
		"with spaces and 1234 numbers",
		"emoji ✓ and unicode é",
		"newline\nokay",
		"tab\tokay",
	}
	for _, in := range cases {
		if got := psEscape(in); got != in {
			t.Errorf("psEscape(%q) should pass through unchanged, got %q", in, got)
		}
	}
}

func TestPsEscape_SingleQuoteIsDoubled(t *testing.T) {
	cases := map[string]string{
		"'":             "''",
		"don't":         "don''t",
		"a'b'c":         "a''b''c",
		"'leading":      "''leading",
		"trailing'":     "trailing''",
		"both'sides'":   "both''sides''",
	}
	for in, want := range cases {
		if got := psEscape(in); got != want {
			t.Errorf("psEscape(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestPsEscape_DoubleQuoteUntouched(t *testing.T) {
	// Inside a PowerShell single-quoted string, double quotes are
	// just literal characters — no escaping required and definitely
	// no doubling.
	in := `say "hello"`
	if got := psEscape(in); got != in {
		t.Errorf("double quotes should not be escaped; got %q", got)
	}
}

func TestPsEscape_BackslashUntouched(t *testing.T) {
	// PowerShell single-quoted strings don't process backslash escapes,
	// so a path like C:\Users\me must come through verbatim.
	in := `C:\Users\me\file.txt`
	if got := psEscape(in); got != in {
		t.Errorf("backslashes should pass through; got %q", got)
	}
}

func TestPsEscape_MixedRealistic(t *testing.T) {
	// Realistic notification body that exercises multiple cases at once.
	in := `It's done — check "C:\report.pdf" (size: 2'500 KB).`
	want := `It''s done — check "C:\report.pdf" (size: 2''500 KB).`
	if got := psEscape(in); got != want {
		t.Errorf("psEscape(%q) = %q, want %q", in, got, want)
	}
}

// Send() shells out to platform-specific commands — testing it directly
// would require mocking exec.Command, which is more ceremony than value
// for the dispatcher here. The platform-routing branches are exercised
// by integration in autotimer / shield. We test psEscape because it's
// pure logic that crosses the trust boundary between Go and PowerShell.
