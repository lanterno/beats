package main

import (
	"net/url"
	"testing"
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
