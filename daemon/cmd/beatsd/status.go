package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/client"
	"github.com/ahmedElghable/beats/daemon/internal/config"
	"github.com/ahmedElghable/beats/daemon/internal/editor"
	"github.com/ahmedElghable/beats/daemon/internal/pair"
)

// runStatus prints what's happening right now: whether a `beatsd run`
// instance is alive, whether a timer is running, and how the API is
// responding. Complements `beatsd doctor` (which validates setup).
//
// Exits with status 1 if pairing or the API call fails — the timer line
// is informational and never fails the command.
func runStatus(cfg *config.Config) error {
	token, err := pair.LoadToken()
	if err != nil {
		fmt.Printf("  pair:   keychain read failed — %v\n", err)
		return err
	}
	if token == "" {
		fmt.Println("  pair:   not paired (run `beatsd pair <code>`)")
		return fmt.Errorf("not paired")
	}
	fmt.Println("  pair:   ok")

	// "Is the daemon running?" proxy: if we can bind the editor listener
	// port, no `beatsd run` is currently up. Free-tier signal — we don't
	// have a side channel into the running process.
	daemonRunning := !portFree(editor.DefaultPort)
	if daemonRunning {
		fmt.Printf("  daemon: %s\n", daemonStatusDetail(editor.DefaultPort))
	} else {
		fmt.Println("  daemon: not running (start with `beatsd run`)")
	}

	c := client.New(cfg.API.BaseURL, token)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	tc, err := c.GetTimerContext(ctx)
	if err != nil {
		fmt.Printf("  api:    unreachable — %v\n", err)
		return err
	}
	fmt.Printf("  api:    %s\n", cfg.API.BaseURL)

	if tc.TimerRunning {
		category := tc.ProjectCategory
		if category == "" {
			category = "—"
		}
		fmt.Printf("  timer:  running on project %s (category: %s)\n",
			truncate(tc.ProjectID, 12), category)
	} else {
		fmt.Println("  timer:  idle")
	}

	fmt.Printf("  flow:   %s\n", flowStatusLine(ctx, c))
	return nil
}

// flowStatusLine returns a one-line summary of the last hour's flow
// data. Pulls from /api/signals/flow-windows/summary so it costs one
// round-trip; "is the flow pipeline producing?" should be cheap to
// answer.
//
// When the last hour is empty, falls back to a 24h count so the user
// can tell the difference between "daemon paired but never producing"
// and "daemon producing earlier today, just quiet right now". Mirrors
// the web FlowHeadline's today→yesterday fallback rule.
//
// On API failure we return a soft "unavailable" message rather than
// surfacing the error to the caller — `beatsd status` succeeded for
// pair/daemon/api/timer; one slow flow call shouldn't fail the
// command. The user already has `beatsd doctor` and `beatsd stats` for
// deeper diagnostics if they need them.
func flowStatusLine(ctx context.Context, c *client.Client) string {
	end := time.Now().UTC()
	start := end.Add(-time.Hour)
	s, err := c.GetFlowWindowsSummary(ctx, start, end, client.FlowWindowsFilter{})
	if err != nil {
		return "unavailable"
	}
	if s.Count > 0 {
		return fmt.Sprintf("%d windows · avg %d · peak %d (last hour)",
			s.Count, int(s.Avg*100), int(s.Peak*100))
	}
	// 1h slice is empty — try 24h to disambiguate "broken pipeline"
	// from "user just unsuspended their laptop". Soft-fall-through on
	// any error here too: the 1h "no windows" message is still useful
	// without the 24h context.
	dayStart := end.Add(-24 * time.Hour)
	d, err := c.GetFlowWindowsSummary(ctx, dayStart, end, client.FlowWindowsFilter{})
	if err != nil || d.Count == 0 {
		return "no windows in the last hour"
	}
	return fmt.Sprintf("no windows in the last hour · %d in last 24h", d.Count)
}

// daemonStatusDetail probes the local editor listener's /health
// endpoint and renders a richer "running" line including the emitted
// flow-window count and uptime when available. Falls back to a plain
// "running" string on any error so the status command stays cheap and
// never wedges behind an unreachable loopback service.
func daemonStatusDetail(port int) string {
	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet,
		fmt.Sprintf("http://127.0.0.1:%d/health", port), nil)
	if err != nil {
		return "running"
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "running"
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "running"
	}
	var body struct {
		WindowsEmitted int64 `json:"windows_emitted"`
		UptimeSec      int64 `json:"uptime_sec"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return "running"
	}
	return fmt.Sprintf("running · %d windows emitted · uptime %s",
		body.WindowsEmitted, formatUptimeShort(body.UptimeSec))
}

// formatUptimeShort renders seconds as "Ns" / "Nm" / "Nh" / "Nd" —
// same rule as the VS Code extension's formatUptime so the cross-
// surface display stays consistent. Multi-day case omits the hours
// here to keep the status line one-glance-readable; the extension's
// tooltip has more room.
func formatUptimeShort(seconds int64) string {
	if seconds < 0 {
		return "0s"
	}
	if seconds < 60 {
		return fmt.Sprintf("%ds", seconds)
	}
	if seconds < 3600 {
		return fmt.Sprintf("%dm", seconds/60)
	}
	if seconds < 86400 {
		return fmt.Sprintf("%dh", seconds/3600)
	}
	return fmt.Sprintf("%dd", seconds/86400)
}

// portFree returns true if 127.0.0.1:port is currently bindable. Used as a
// cheap "is another beatsd already running?" check.
func portFree(port int) bool {
	addr := fmt.Sprintf("127.0.0.1:%d", port)
	l, err := net.Listen("tcp", addr)
	if err != nil {
		return false
	}
	_ = l.Close()
	return true
}

// truncate returns at most n chars of s, with an ellipsis on overflow.
// Project IDs are MongoDB ObjectIds (24 chars) — truncating to 12 keeps
// the status row readable while staying long enough to disambiguate.
func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	if n < 1 {
		return ""
	}
	return s[:n] + "…"
}
