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
//
// When `asJSON` is true, every section ships in a single object instead
// of the human form. The shape is stable — fields that couldn't be
// populated render as null / false / 0 rather than disappearing — so
// jq scripts and the companion's status widget don't have to guard
// against missing keys.
func runStatus(cfg *config.Config, asJSON bool) error {
	report, runErr := collectStatus(cfg)

	if asJSON {
		out, jerr := formatStatusJSON(report)
		if jerr != nil {
			return jerr
		}
		fmt.Print(out)
		return runErr
	}

	printStatusHuman(cfg, report)
	return runErr
}

// statusReport is the structured snapshot collectStatus produces.
// Each section's "ok-ness" (pair / daemon / api) lives next to its
// detail fields so the JSON form is one round-trip readable. The
// shape is the public --json contract — adding fields is fine,
// renaming or removing them is a breaking change.
type statusReport struct {
	Paired bool         `json:"paired"`
	Daemon daemonStatus `json:"daemon"`
	API    apiStatus    `json:"api"`
	Timer  timerStatus  `json:"timer"`
	Flow   flowStatus   `json:"flow"`
}

type daemonStatus struct {
	Running        bool  `json:"running"`
	UptimeSec      int64 `json:"uptime_sec"`
	WindowsEmitted int64 `json:"windows_emitted"`
}

type apiStatus struct {
	URL       string `json:"url"`
	Reachable bool   `json:"reachable"`
	Error     string `json:"error,omitempty"`
}

type timerStatus struct {
	Running         bool   `json:"running"`
	ProjectID       string `json:"project_id,omitempty"`
	ProjectCategory string `json:"project_category,omitempty"`
}

type flowStatus struct {
	WindowMinutes    int     `json:"window_minutes"`
	Count            int     `json:"count"`
	Avg              float64 `json:"avg"`
	Peak             float64 `json:"peak"`
	Count24hFallback int     `json:"count_24h_fallback,omitempty"`
	Available        bool    `json:"available"`
}

// collectStatus walks the same pair/daemon/api/timer/flow probes
// the human form prints, but returns a structured report instead
// of writing to stdout. The error mirrors the exit-code rule: nil
// when everything that should succeed did, else a sentinel.
//
// Extracted so both --json and the human form consume the same
// snapshot — drift between the two would otherwise be a class of
// bug we'd ship without noticing.
func collectStatus(cfg *config.Config) (statusReport, error) {
	report := statusReport{
		API:  apiStatus{URL: cfg.API.BaseURL},
		Flow: flowStatus{WindowMinutes: 60},
	}

	token, err := pair.LoadToken()
	if err != nil {
		return report, err
	}
	if token == "" {
		return report, fmt.Errorf("not paired")
	}
	report.Paired = true

	if !portFree(editor.DefaultPort) {
		report.Daemon.Running = true
		report.Daemon.UptimeSec, report.Daemon.WindowsEmitted = probeOwnDaemonHealth(editor.DefaultPort)
	}

	c := client.New(cfg.API.BaseURL, token)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	tc, err := c.GetTimerContext(ctx)
	if err != nil {
		report.API.Error = err.Error()
		return report, err
	}
	report.API.Reachable = true
	report.Timer = timerStatus{
		Running:         tc.TimerRunning,
		ProjectID:       tc.ProjectID,
		ProjectCategory: tc.ProjectCategory,
	}

	report.Flow = collectFlowStatus(ctx, c)
	return report, nil
}

// probeOwnDaemonHealth fetches uptime + windows-emitted from the
// loopback /health endpoint. Returns zeroes on any failure so the
// caller can still mark the daemon as "running" (we know the port
// is bound) without claiming a specific uptime we don't have.
func probeOwnDaemonHealth(port int) (uptimeSec int64, windowsEmitted int64) {
	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet,
		fmt.Sprintf("http://127.0.0.1:%d/health", port), nil)
	if err != nil {
		return 0, 0
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return 0, 0
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return 0, 0
	}
	var body struct {
		WindowsEmitted int64 `json:"windows_emitted"`
		UptimeSec      int64 `json:"uptime_sec"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return 0, 0
	}
	return body.UptimeSec, body.WindowsEmitted
}

// collectFlowStatus is the structured form of flowStatusLine —
// returns a flowStatus with count/avg/peak (last hour) plus the
// 24h fallback count when the 1h slice is empty. `Available` is
// false when the API call failed; the human form renders this as
// "unavailable" rather than "0 windows".
func collectFlowStatus(ctx context.Context, c *client.Client) flowStatus {
	out := flowStatus{WindowMinutes: 60}
	end := time.Now().UTC()
	start := end.Add(-time.Hour)
	s, err := c.GetFlowWindowsSummary(ctx, start, end, client.FlowWindowsFilter{})
	if err != nil {
		return out
	}
	out.Available = true
	if s.Count > 0 {
		out.Count = s.Count
		out.Avg = s.Avg
		out.Peak = s.Peak
		return out
	}
	// 1h slice empty — chase a 24h count for "broken pipeline" vs
	// "just-unsuspended laptop" disambiguation. Soft-fall-through
	// on errors: still useful without the 24h context.
	dayStart := end.Add(-24 * time.Hour)
	d, derr := c.GetFlowWindowsSummary(ctx, dayStart, end, client.FlowWindowsFilter{})
	if derr == nil {
		out.Count24hFallback = d.Count
	}
	return out
}

// printStatusHuman emits the line-oriented status output.
// Behavior matches the pre-JSON-mode runStatus byte-for-byte
// for the healthy paths; the only added decoration is the
// "connected but no emissions" diagnostic line that mirrors
// the VS Code extension's tooltip warning.
func printStatusHuman(cfg *config.Config, r statusReport) {
	if !r.Paired {
		fmt.Println("  pair:   not paired (run `beatsd pair <code>`)")
		return
	}
	fmt.Println("  pair:   ok")

	if r.Daemon.Running {
		if r.Daemon.UptimeSec > 0 {
			fmt.Printf("  daemon: running · %d windows emitted · uptime %s\n",
				r.Daemon.WindowsEmitted, formatUptimeShort(r.Daemon.UptimeSec))
		} else {
			fmt.Println("  daemon: running")
		}
		if isStaleNoEmissions(r.Daemon) {
			fmt.Println("          ⚠ no flow windows emitted in this session — check Accessibility permission")
		}
	} else {
		fmt.Println("  daemon: not running (start with `beatsd run`)")
	}

	if !r.API.Reachable {
		fmt.Printf("  api:    unreachable — %s\n", r.API.Error)
		return
	}
	fmt.Printf("  api:    %s\n", cfg.API.BaseURL)

	if r.Timer.Running {
		category := r.Timer.ProjectCategory
		if category == "" {
			category = "—"
		}
		fmt.Printf("  timer:  running on project %s (category: %s)\n",
			truncate(r.Timer.ProjectID, 12), category)
	} else {
		fmt.Println("  timer:  idle")
	}

	fmt.Printf("  flow:   %s\n", renderFlowLine(r.Flow))
}

// renderFlowLine maps a flowStatus to the same human string the
// previous flowStatusLine produced. Unit-testable without an
// httptest fixture.
func renderFlowLine(f flowStatus) string {
	if !f.Available {
		return "unavailable"
	}
	if f.Count > 0 {
		return fmt.Sprintf("%d windows · avg %d · peak %d (last hour)",
			f.Count, int(f.Avg*100), int(f.Peak*100))
	}
	if f.Count24hFallback > 0 {
		return fmt.Sprintf("no windows in the last hour · %d in last 24h", f.Count24hFallback)
	}
	return "no windows in the last hour"
}

// isStaleNoEmissions reports whether the daemon has been up long
// enough that "0 windows emitted" looks like a real failure (likely
// Accessibility permission revoked mid-session) rather than a
// freshly-started daemon still flushing its first window. 90s
// matches the daemon's internal Accessibility re-probe cadence;
// keeping the surface signals aligned means the human + VS Code
// tooltip diagnostics flag the same condition at the same moment.
//
// Cross-language parity with isStaleNoEmissions in
// integrations/vscode-beats/src/statusBar.ts.
func isStaleNoEmissions(d daemonStatus) bool {
	return d.Running && d.WindowsEmitted == 0 && d.UptimeSec >= 90
}

// formatStatusJSON renders the report as a JSON object with a
// trailing newline. Same shape on success and on failure paths so
// jq consumers don't have to guard against missing keys.
func formatStatusJSON(r statusReport) (string, error) {
	b, err := json.MarshalIndent(r, "", "  ")
	if err != nil {
		return "", fmt.Errorf("encode JSON: %w", err)
	}
	return string(b) + "\n", nil
}

// flowStatusLine returns the same one-line summary the human form
// has always rendered. Now a thin wrapper over collectFlowStatus +
// renderFlowLine so the structured (JSON) and string (table) paths
// can never drift. Kept as a named export for the existing test
// suite, which exercises the full pipeline through this entry
// point.
func flowStatusLine(ctx context.Context, c *client.Client) string {
	return renderFlowLine(collectFlowStatus(ctx, c))
}

// daemonStatusDetail returns the human "running · N windows
// emitted · uptime Xm" line. Kept as a wrapper for the same
// reason flowStatusLine is — existing tests exercise it
// end-to-end and the structured form (probeOwnDaemonHealth)
// powers the JSON path.
func daemonStatusDetail(port int) string {
	uptime, emitted := probeOwnDaemonHealth(port)
	if uptime == 0 && emitted == 0 {
		return "running"
	}
	return fmt.Sprintf("running · %d windows emitted · uptime %s",
		emitted, formatUptimeShort(uptime))
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
