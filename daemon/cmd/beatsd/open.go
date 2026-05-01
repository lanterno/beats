package main

import (
	"fmt"
	"net/url"
	"os"
	"os/exec"
	"runtime"
	"strings"

	"github.com/ahmedElghable/beats/daemon/internal/config"
)

// OpenFilter narrows the deep-link URL `beatsd open` opens. Each
// field maps to the matching chip the user could set on the web
// Insights page; all three are AND-composed at the page level via
// useUrlParam.
type OpenFilter struct {
	Repo     string
	Language string
	Bundle   string
}

// runOpen launches the system browser at the configured Beats web UI's
// Insights page, optionally deep-linked to a filtered view. Mirrors
// the VS Code extension's "Beats: Open Insights" command — terminal
// users get the same one-keystroke jump to analytics without leaving
// the shell.
//
// All filter fields are optional; an empty filter opens the unfiltered
// view. We don't auto-detect cwd here because a user running `beatsd
// open` from a directory that ISN'T a paired editor workspace would
// land on a confusingly-empty filtered view.
//
// When `printOnly` is true, the URL is written to stdout instead of
// launching the browser. Designed for shell pipelines:
//
//	beatsd open --repo $(pwd) --print | pbcopy
//	open "$(beatsd open --print)"
//
// — and as a fallback for users without a default browser configured.
func runOpen(cfg *config.Config, filter OpenFilter, printOnly bool) error {
	url := buildInsightsURL(cfg.UI.BaseURL, filter)
	if printOnly {
		// Bare URL on stdout, no decoration. Pipeable.
		fmt.Println(url)
		return nil
	}
	if err := openBrowser(url); err != nil {
		// Non-fatal — print the URL anyway so the user can copy/paste.
		fmt.Printf("could not open browser automatically: %v\n", err)
		fmt.Printf("URL: %s\n", url)
		return nil
	}
	fmt.Printf("opening %s\n", url)
	return nil
}

// buildInsightsURL is the testable inner of runOpen. Mirrors the
// behavior of the VS Code extension's buildInsightsUrl (in
// integrations/vscode-beats/src/insightsUrl.ts) and the home
// FlowHeadline's pill onClick handlers — so a deep link from any of
// those surfaces lands on the exact same page state.
//
// Param order is alphabetical (bundle, language, repo) — Go's
// url.Values encodes that way deterministically, which keeps URLs
// stable across daemon versions for diffing in shell history.
func buildInsightsURL(base string, filter OpenFilter) string {
	trimmed := strings.TrimRight(base, "/")
	q := url.Values{}
	if filter.Bundle != "" {
		q.Set("bundle", filter.Bundle)
	}
	if filter.Language != "" {
		q.Set("language", filter.Language)
	}
	if filter.Repo != "" {
		q.Set("repo", filter.Repo)
	}
	if len(q) == 0 {
		return trimmed + "/insights"
	}
	return trimmed + "/insights?" + q.Encode()
}

// resolveHereRepo returns the path that should be used as the
// `--repo` filter when the user passes `--here`. Tries to resolve
// the git toplevel from the current working directory so a user
// running `beatsd open --here` from any subdirectory of the repo
// gets the same canonical path the daemon's editor heartbeats
// emit. Falls back to the bare cwd when `git rev-parse` fails
// (cwd isn't inside a git work tree, or git isn't installed) —
// the URL still opens, just with a less-canonical path.
//
// Returns an error only when even os.Getwd() fails, which
// shouldn't happen in any practical setup but is worth surfacing
// so we don't silently open the unfiltered Insights view.
func resolveHereRepo() (string, error) {
	cwd, err := os.Getwd()
	if err != nil {
		return "", fmt.Errorf("could not determine current directory: %w", err)
	}
	if root, ok := gitToplevel(cwd); ok {
		return root, nil
	}
	return cwd, nil
}

// gitToplevel runs `git rev-parse --show-toplevel` from [dir] and
// returns the resolved repo root on success. Extracted so unit
// tests can call it with a known-git directory (this repo's own
// path) and assert the contract without mocking exec.Command.
func gitToplevel(dir string) (string, bool) {
	cmd := exec.Command("git", "-C", dir, "rev-parse", "--show-toplevel")
	out, err := cmd.Output()
	if err != nil {
		return "", false
	}
	root := strings.TrimSpace(string(out))
	if root == "" {
		return "", false
	}
	return root, true
}

// openBrowser invokes the system's URL handler. Cross-platform shim —
// the VS Code extension uses vscode.env.openExternal which abstracts
// this away, but the daemon has to dispatch by GOOS.
func openBrowser(url string) error {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("open", url)
	case "linux":
		cmd = exec.Command("xdg-open", url)
	case "windows":
		cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", url)
	default:
		return fmt.Errorf("unsupported platform: %s", runtime.GOOS)
	}
	return cmd.Start()
}
