package main

import (
	"os"
	"strings"
	"testing"
)

// run returns an exit code instead of calling os.Exit, which is the whole
// reason these tests can exist — the dispatch used to live in main() and could
// only be exercised by starting a process.

func captureStd(t *testing.T, fn func() int) (code int, stdout, stderr string) {
	t.Helper()

	outR, outW, err := os.Pipe()
	if err != nil {
		t.Fatalf("pipe: %v", err)
	}
	errR, errW, err := os.Pipe()
	if err != nil {
		t.Fatalf("pipe: %v", err)
	}

	origOut, origErr := os.Stdout, os.Stderr
	os.Stdout, os.Stderr = outW, errW
	t.Cleanup(func() { os.Stdout, os.Stderr = origOut, origErr })

	code = fn()

	outW.Close()
	errW.Close()
	var ob, eb strings.Builder
	buf := make([]byte, 4096)
	for _, pair := range []struct {
		r *os.File
		b *strings.Builder
	}{{outR, &ob}, {errR, &eb}} {
		for {
			n, readErr := pair.r.Read(buf)
			pair.b.Write(buf[:n])
			if readErr != nil {
				break
			}
		}
		pair.r.Close()
	}
	return code, ob.String(), eb.String()
}

func TestRun_NoArgsPrintsUsageAndFails(t *testing.T) {
	code, _, stderr := captureStd(t, func() int { return run(nil) })

	if code != 1 {
		t.Errorf("expected exit 1 with no command, got %d", code)
	}
	if !strings.Contains(stderr, "beatsd") {
		t.Errorf("expected usage on stderr, got: %q", stderr)
	}
}

func TestRun_HelpSucceedsOnStdout(t *testing.T) {
	// Asking for help is not an error, and the text goes to stdout so
	// `beatsd --help | grep` works.
	for _, arg := range []string{"--help", "-h", "help"} {
		code, stdout, _ := captureStd(t, func() int { return run([]string{arg}) })

		if code != 0 {
			t.Errorf("%s: expected exit 0, got %d", arg, code)
		}
		if !strings.Contains(stdout, "beatsd") {
			t.Errorf("%s: expected usage on stdout, got: %q", arg, stdout)
		}
	}
}

func TestRun_HelpIsRecognizedAfterACommand(t *testing.T) {
	// `beatsd recent --help` must print help rather than trying to run the
	// command and failing on "not paired".
	code, stdout, _ := captureStd(t, func() int { return run([]string{"recent", "--help"}) })

	if code != 0 {
		t.Errorf("expected exit 0, got %d", code)
	}
	if !strings.Contains(stdout, "beatsd") {
		t.Errorf("expected usage on stdout, got: %q", stdout)
	}
}

func TestRun_UnknownCommandSuggests(t *testing.T) {
	code, _, stderr := captureStd(t, func() int { return run([]string{"stauts"}) })

	if code != 1 {
		t.Errorf("expected exit 1 for an unknown command, got %d", code)
	}
	if !strings.Contains(stderr, "unknown command") {
		t.Errorf("expected an unknown-command message, got: %q", stderr)
	}
	if !strings.Contains(stderr, "status") {
		t.Errorf("expected a suggestion of `status`, got: %q", stderr)
	}
}
