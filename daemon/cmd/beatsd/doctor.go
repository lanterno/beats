package main

import (
	"context"
	"fmt"
	"net"
	"strings"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/client"
	"github.com/ahmedElghable/beats/daemon/internal/collector"
	"github.com/ahmedElghable/beats/daemon/internal/config"
	"github.com/ahmedElghable/beats/daemon/internal/editor"
	"github.com/ahmedElghable/beats/daemon/internal/pair"
)

// runDoctor checks every prerequisite the run loop depends on and prints a
// human-readable report. Exits with status 1 if any check failed so users
// can `beatsd doctor && beatsd run` in startup scripts.
//
// Output format is intentionally line-oriented (no curses, no progress
// bars) so it pipes well into journals, screenshots, and Claude pastes.
func runDoctor(cfg *config.Config) error {
	checks := []doctorCheck{
		{name: "Device token in keychain", fn: checkToken},
		{name: "API reachable", fn: func() (string, error) { return checkAPI(cfg) }},
		{name: "Editor listener port", fn: checkEditorPort},
		{name: "Input event tap (cadence)", fn: checkEventTap},
	}

	allPassed := true
	for _, c := range checks {
		detail, err := c.fn()
		mark := "✓"
		if err != nil {
			mark = "✗"
			allPassed = false
		}
		fmt.Printf("  %s  %s", mark, c.name)
		if detail != "" {
			fmt.Printf(" — %s", detail)
		}
		if err != nil {
			fmt.Printf("\n      %s", err.Error())
		}
		fmt.Println()
	}

	fmt.Println()
	if allPassed {
		fmt.Println("All checks passed. `beatsd run` should work.")
		return nil
	}
	return fmt.Errorf("one or more checks failed")
}

type doctorCheck struct {
	name string
	// fn returns a short status detail (e.g. "europe-west1, 42ms") and an
	// error if the check failed. detail is shown either way; err marks the
	// row as failed.
	fn func() (string, error)
}

// checkToken: is a paired device token present in the keychain?
func checkToken() (string, error) {
	token, err := pair.LoadToken()
	if err != nil {
		return "", fmt.Errorf("keychain read failed: %w", err)
	}
	if token == "" {
		return "missing", fmt.Errorf("not paired — run `beatsd pair <code>`")
	}
	// Don't print the token; it's a credential. Show a tiny prefix as a
	// confirmation that *some* token is present.
	prefix := token
	if len(prefix) > 6 {
		prefix = prefix[:6] + "…"
	}
	return prefix, nil
}

// checkAPI: can the daemon authenticate against the configured API?
// Uses the heartbeat endpoint which is cheap and validates the token.
func checkAPI(cfg *config.Config) (string, error) {
	token, err := pair.LoadToken()
	if err != nil || token == "" {
		return "", fmt.Errorf("skipped: no token")
	}
	c := client.New(cfg.API.BaseURL, token)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	start := time.Now()
	if err := c.PostHeartbeat(ctx); err != nil {
		return cfg.API.BaseURL, err
	}
	return fmt.Sprintf("%s (%dms)", cfg.API.BaseURL, time.Since(start).Milliseconds()), nil
}

// checkEditorPort: is the loopback port for editor heartbeats free? The
// daemon will gracefully log + continue if it's taken, but it means the
// VS Code extension can't deliver heartbeats.
func checkEditorPort() (string, error) {
	addr := fmt.Sprintf("127.0.0.1:%d", editor.DefaultPort)
	l, err := net.Listen("tcp", addr)
	if err != nil {
		return addr, fmt.Errorf("port in use — another beatsd already running?")
	}
	_ = l.Close()
	return fmt.Sprintf("%s available", addr), nil
}

// checkEventTap: is macOS Accessibility permission granted? On non-darwin
// we report a stub-fallback note so the user knows the feature is darwin-only.
func checkEventTap() (string, error) {
	getAndReset, stop, err := collector.StartEventTap()
	if err != nil {
		// Non-darwin platforms always return ErrEventTapNotAvailable from
		// the stub. Treat that as informational, not a failure — cadence
		// just falls back to 0.5.
		if strings.Contains(err.Error(), "not available on this platform") ||
			err.Error() == "event tap not available" {
			return "stub fallback (cadence will default to 0.5)", nil
		}
		return "", fmt.Errorf("%w — grant via System Settings → Privacy & Security → Accessibility", err)
	}
	if stop != nil {
		stop()
	}
	if getAndReset != nil {
		_ = getAndReset()
	}
	return "active (real input counting)", nil
}
