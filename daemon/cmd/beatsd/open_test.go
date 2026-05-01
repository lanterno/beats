package main

import (
	"io"
	"net/url"
	"os"
	"strings"
	"testing"

	"github.com/ahmedElghable/beats/daemon/internal/config"
)

// Cross-language parity check: each assertion here should match the
// equivalent in the VS Code extension's buildInsightsUrl test
// (integrations/vscode-beats/src/insightsUrl.test.ts). A user opening
// from `beatsd open` and from ⌘⇧P "Beats: Open Insights" should land
// at the same URL given the same inputs.

func TestBuildInsightsURL_BareWhenNoRepo(t *testing.T) {
	got := buildInsightsURL("http://localhost:8080", "")
	want := "http://localhost:8080/insights"
	if got != want {
		t.Errorf("expected %q, got %q", want, got)
	}
}

func TestBuildInsightsURL_AppendsRepoQueryParam(t *testing.T) {
	got := buildInsightsURL("http://localhost:8080", "/Users/me/code/beats")
	want := "http://localhost:8080/insights?repo=%2FUsers%2Fme%2Fcode%2Fbeats"
	if got != want {
		t.Errorf("expected %q, got %q", want, got)
	}
}

func TestBuildInsightsURL_StripsTrailingSlashOnBase(t *testing.T) {
	// Self-hosted users sometimes set base with a trailing slash.
	// Without normalization we'd produce //insights — ugly, technically
	// works in browsers but reads as a config bug in logs.
	got := buildInsightsURL("https://beats.example.com/", "")
	want := "https://beats.example.com/insights"
	if got != want {
		t.Errorf("expected %q, got %q", want, got)
	}
}

func TestBuildInsightsURL_EncodesSpecialCharsInRepoPath(t *testing.T) {
	// Spaces happen on macOS user folders; & and = are pathological
	// but possible. The web's useUrlParam reads via URLSearchParams
	// which decodes — verify the chain matches.
	got := buildInsightsURL("http://localhost:8080", "/Users/me/My Code/x&y=z")
	parsed, err := url.Parse(got)
	if err != nil {
		t.Fatalf("buildInsightsURL produced unparseable output: %v", err)
	}
	if parsed.Path != "/insights" {
		t.Errorf("expected /insights path, got %q", parsed.Path)
	}
	if parsed.Query().Get("repo") != "/Users/me/My Code/x&y=z" {
		t.Errorf("repo round-trip failed, got %q", parsed.Query().Get("repo"))
	}
}

// captureStdout redirects os.Stdout for the duration of fn and returns
// what was written. Pure stdlib (no testify / mocks added).
func captureStdout(t *testing.T, fn func()) string {
	t.Helper()
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatalf("os.Pipe: %v", err)
	}
	orig := os.Stdout
	os.Stdout = w
	defer func() { os.Stdout = orig }()

	fn()
	_ = w.Close()
	out, _ := io.ReadAll(r)
	return string(out)
}

func TestRunOpen_PrintPathWritesBareURL(t *testing.T) {
	// `beatsd open --print` is meant for shell pipelines —
	// `beatsd open --print | pbcopy` should put exactly the URL on
	// the clipboard, no decoration. Lock that in: stdout is the bare
	// URL plus a single trailing newline (from fmt.Println).
	cfg := &config.Config{}
	cfg.UI.BaseURL = "http://localhost:8080"

	out := captureStdout(t, func() {
		_ = runOpen(cfg, "/Users/me/code/beats", true)
	})

	want := "http://localhost:8080/insights?repo=%2FUsers%2Fme%2Fcode%2Fbeats\n"
	if out != want {
		t.Errorf("expected exact %q, got %q", want, out)
	}
	// Specifically: the launch path's "opening <url>" message must
	// NOT leak into --print output. A pipeline with that prefix would
	// produce a malformed URL on the clipboard.
	if strings.Contains(out, "opening") {
		t.Errorf("expected no 'opening' decoration in --print output, got: %q", out)
	}
}

func TestRunOpen_PrintPathPipeableWithNoRepo(t *testing.T) {
	// Bare unfiltered URL when no --repo is given. Same shape pattern
	// — exactly the URL plus a newline — so scripts that pipe the
	// output don't have to strip whitespace.
	cfg := &config.Config{}
	cfg.UI.BaseURL = "http://localhost:8080"

	out := captureStdout(t, func() {
		_ = runOpen(cfg, "", true)
	})

	if out != "http://localhost:8080/insights\n" {
		t.Errorf("unexpected output: %q", out)
	}
}
