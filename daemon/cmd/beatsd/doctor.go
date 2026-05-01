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
		{name: "Flow data flowing", fn: func() (string, error) { return checkFlowData(cfg) }},
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

// checkFlowData: hits /api/signals/flow-windows/summary for the last
// hour to validate the full analytics pipeline (keychain → API →
// flow windows). Pure setup probes (token + API + listener) only
// confirm the daemon CAN talk to the API; this confirms the daemon
// IS getting flow data through.
//
// Detail-only — never fails. A user running `beatsd doctor` right
// after `beatsd pair` legitimately has zero windows; failing on that
// would block startup scripts that chain `beatsd doctor && beatsd
// run`. The detail string surfaces the count so the user can spot a
// mismatch with the daemon they expect to be running.
func checkFlowData(cfg *config.Config) (string, error) {
	token, err := pair.LoadToken()
	if err != nil || token == "" {
		return "skipped: no token", nil
	}
	c := client.New(cfg.API.BaseURL, token)
	return flowDataDetail(c), nil
}

// flowDataDetail is the testable inner of checkFlowData. Splitting out
// the keychain access lets tests stand up an httptest server and pass
// a real client.Client without writing a token to the user's
// keychain.
func flowDataDetail(c *client.Client) string {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	end := time.Now().UTC()
	start := end.Add(-time.Hour)
	s, err := c.GetFlowWindowsSummary(ctx, start, end, client.FlowWindowsFilter{})
	if err != nil {
		return "summary fetch failed"
	}
	if s.Count == 0 {
		return "no windows in the last hour (start `beatsd run` if not already running)"
	}
	return fmt.Sprintf("%d windows · avg %d (last hour)", s.Count, int(s.Avg*100))
}

// checkEventTap: is macOS Accessibility permission granted? Uses
// ProbeEventTap rather than the full StartEventTap so doctor doesn't have
// to spin up + tear down a CFRunLoop for a yes/no answer.
func checkEventTap() (string, error) {
	if err := collector.ProbeEventTap(); err != nil {
		// Non-darwin platforms always report unavailable from the stub.
		// Treat that as informational, not a failure — cadence just falls
		// back to 0.5.
		if strings.Contains(err.Error(), "not available on this platform") ||
			err.Error() == "event tap not available" {
			return "stub fallback (cadence will default to 0.5)", nil
		}
		return "", fmt.Errorf("%w — grant via System Settings → Privacy & Security → Accessibility", err)
	}
	return "available", nil
}
