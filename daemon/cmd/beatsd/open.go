package main

import (
	"fmt"
	"net/url"
	"os/exec"
	"runtime"
	"strings"

	"github.com/ahmedElghable/beats/daemon/internal/config"
)

// runOpen launches the system browser at the configured Beats web UI's
// Insights page, optionally deep-linked to a repo path. Mirrors the VS
// Code extension's "Beats: Open Insights" command — terminal users get
// the same one-keystroke jump to analytics without leaving the shell.
//
// `repo` is the editor_repo path to filter by; pass an empty string for
// the unfiltered view. We don't auto-detect cwd here because a user
// running `beatsd open` from a directory that ISN'T a paired editor
// workspace would land on a confusingly-empty filtered view.
func runOpen(cfg *config.Config, repo string) error {
	url := buildInsightsURL(cfg.UI.BaseURL, repo)
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
// integrations/vscode-beats/src/insightsUrl.ts) so a deep link from
// either the editor command or the daemon CLI lands on the same page
// state the user would see by clicking a chip.
func buildInsightsURL(base, repo string) string {
	trimmed := strings.TrimRight(base, "/")
	if repo == "" {
		return trimmed + "/insights"
	}
	return trimmed + "/insights?repo=" + url.QueryEscape(repo)
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
