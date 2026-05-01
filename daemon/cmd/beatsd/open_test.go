package main

import (
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

func TestBuildInsightsURL_BareWhenNoFilter(t *testing.T) {
	got := buildInsightsURL("http://localhost:8080", OpenFilter{})
	want := "http://localhost:8080/insights"
	if got != want {
		t.Errorf("expected %q, got %q", want, got)
	}
}

func TestBuildInsightsURL_AppendsRepoQueryParam(t *testing.T) {
	got := buildInsightsURL("http://localhost:8080", OpenFilter{Repo: "/Users/me/code/beats"})
	want := "http://localhost:8080/insights?repo=%2FUsers%2Fme%2Fcode%2Fbeats"
	if got != want {
		t.Errorf("expected %q, got %q", want, got)
	}
}

func TestBuildInsightsURL_StripsTrailingSlashOnBase(t *testing.T) {
	// Self-hosted users sometimes set base with a trailing slash.
	// Without normalization we'd produce //insights — ugly, technically
	// works in browsers but reads as a config bug in logs.
	got := buildInsightsURL("https://beats.example.com/", OpenFilter{})
	want := "https://beats.example.com/insights"
	if got != want {
		t.Errorf("expected %q, got %q", want, got)
	}
}

func TestBuildInsightsURL_EncodesSpecialCharsInRepoPath(t *testing.T) {
	// Spaces happen on macOS user folders; & and = are pathological
	// but possible. The web's useUrlParam reads via URLSearchParams
	// which decodes — verify the chain matches.
	got := buildInsightsURL("http://localhost:8080", OpenFilter{Repo: "/Users/me/My Code/x&y=z"})
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

func TestBuildInsightsURL_LanguageOnly(t *testing.T) {
	got := buildInsightsURL("http://localhost:8080", OpenFilter{Language: "go"})
	parsed, _ := url.Parse(got)
	if parsed.Query().Get("language") != "go" {
		t.Errorf("expected ?language=go, got %q", got)
	}
	if parsed.Query().Has("repo") || parsed.Query().Has("bundle") {
		t.Errorf("expected only the language param, got %q", got)
	}
}

func TestBuildInsightsURL_BundleOnly(t *testing.T) {
	got := buildInsightsURL("http://localhost:8080", OpenFilter{Bundle: "com.microsoft.VSCode"})
	parsed, _ := url.Parse(got)
	if parsed.Query().Get("bundle") != "com.microsoft.VSCode" {
		t.Errorf("expected ?bundle=com.microsoft.VSCode, got %q", got)
	}
}

func TestBuildInsightsURL_AllThreeAxesCompose(t *testing.T) {
	// AND-compose: a user wants "today's Go work in the beats repo
	// inside VS Code". All three should land in the URL.
	got := buildInsightsURL("http://localhost:8080", OpenFilter{
		Repo:     "/Users/me/code/beats",
		Language: "go",
		Bundle:   "com.microsoft.VSCode",
	})
	parsed, err := url.Parse(got)
	if err != nil {
		t.Fatalf("unparseable: %v", err)
	}
	if parsed.Query().Get("repo") != "/Users/me/code/beats" {
		t.Errorf("repo missing, got %q", got)
	}
	if parsed.Query().Get("language") != "go" {
		t.Errorf("language missing, got %q", got)
	}
	if parsed.Query().Get("bundle") != "com.microsoft.VSCode" {
		t.Errorf("bundle missing, got %q", got)
	}
}

func TestBuildInsightsURL_OrderIsStable(t *testing.T) {
	// url.Values.Encode sorts keys alphabetically — so two consecutive
	// `beatsd open --repo X --language Y --print` runs produce
	// byte-identical URLs (good for shell history grepping). Lock
	// it in by checking the literal ordering: bundle < language <
	// repo alphabetically.
	got := buildInsightsURL("http://localhost:8080", OpenFilter{
		Repo: "r", Language: "l", Bundle: "b",
	})
	want := "http://localhost:8080/insights?bundle=b&language=l&repo=r"
	if got != want {
		t.Errorf("expected stable ordering %q, got %q", want, got)
	}
}

// captureStdout is a thin wrapper around captureFile (in help_test.go)
// that always targets os.Stdout. Kept as a separate name only to make
// existing callsites read clearly — the verb here is "capture stdout"
// not "capture this *os.File pointer".
func captureStdout(t *testing.T, fn func()) string {
	t.Helper()
	return captureFile(t, &os.Stdout, fn)
}

func TestRunOpen_PrintPathWritesBareURL(t *testing.T) {
	// `beatsd open --print` is meant for shell pipelines —
	// `beatsd open --print | pbcopy` should put exactly the URL on
	// the clipboard, no decoration. Lock that in: stdout is the bare
	// URL plus a single trailing newline (from fmt.Println).
	cfg := &config.Config{}
	cfg.UI.BaseURL = "http://localhost:8080"

	out := captureStdout(t, func() {
		_ = runOpen(cfg, OpenFilter{Repo: "/Users/me/code/beats"}, true)
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

// --- --here / resolveHereRepo / gitToplevel ---

func TestGitToplevel_FromInsideThisRepoReturnsRoot(t *testing.T) {
	// We run from cmd/beatsd/, three levels deep in the beats repo.
	// gitToplevel should walk up to the actual top-level. Using the
	// test's own location is a reliable real-git fixture without
	// having to scaffold a temporary repo.
	cwd, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	root, ok := gitToplevel(cwd)
	if !ok {
		t.Skip("git not on PATH or this checkout isn't a git repo; skipping")
	}
	// Sanity: the resolved root should be a parent of cwd.
	if !strings.HasPrefix(cwd, root) {
		t.Errorf("expected cwd %q to live under resolved root %q", cwd, root)
	}
	// The repo's daemon/cmd/beatsd subtree must exist below the root,
	// confirming we got the project root and not some accidental
	// nested git submodule. Check via os.Stat to avoid hard-coding
	// the absolute path.
	if _, err := os.Stat(root + "/daemon/cmd/beatsd"); err != nil {
		t.Errorf("expected daemon/cmd/beatsd under resolved root, got: %v", err)
	}
}

func TestGitToplevel_OutsideAnyRepoReturnsNotOk(t *testing.T) {
	// /tmp on macOS / Linux is not inside a git work tree. The
	// helper must report (not ok) so resolveHereRepo can fall back
	// to the bare cwd. Skip on platforms where /tmp doesn't exist
	// (windows runs unlikely but defensive).
	if _, err := os.Stat("/tmp"); err != nil {
		t.Skip("no /tmp on this platform")
	}
	if _, ok := gitToplevel("/tmp"); ok {
		t.Errorf("expected /tmp to not be inside any git repo")
	}
}

func TestResolveHereRepo_ReturnsNonEmptyPath(t *testing.T) {
	// Whatever cwd resolves to (git toplevel or bare cwd), the
	// result must be a non-empty absolute path so the URL builder
	// can encode it as ?repo=…
	got, err := resolveHereRepo()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got == "" {
		t.Errorf("expected a non-empty path, got %q", got)
	}
	if !strings.HasPrefix(got, "/") && !(len(got) >= 2 && got[1] == ':') {
		// Posix absolute (/...) or Windows drive (C:\...).
		t.Errorf("expected an absolute path, got %q", got)
	}
}

func TestRunOpen_PrintPathPipeableWithNoRepo(t *testing.T) {
	// Bare unfiltered URL when no --repo is given. Same shape pattern
	// — exactly the URL plus a newline — so scripts that pipe the
	// output don't have to strip whitespace.
	cfg := &config.Config{}
	cfg.UI.BaseURL = "http://localhost:8080"

	out := captureStdout(t, func() {
		_ = runOpen(cfg, OpenFilter{}, true)
	})

	if out != "http://localhost:8080/insights\n" {
		t.Errorf("unexpected output: %q", out)
	}
}
