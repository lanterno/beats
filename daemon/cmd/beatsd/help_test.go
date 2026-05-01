package main

import (
	"os"
	"strings"
	"testing"
)

// captureFile redirects either os.Stdout or os.Stderr for the duration
// of fn and returns what was written. Pure stdlib — same trick the
// open_test.go captureStdout helper uses, factored here so writeUsage
// can be tested against both streams.
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
	buf := make([]byte, 64*1024)
	n, _ := r.Read(buf)
	return string(buf[:n])
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
