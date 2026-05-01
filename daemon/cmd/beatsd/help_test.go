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
