package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/client"
)

// statusFlowFixture spins up an httptest server that responds to
// GET /api/signals/flow-windows/summary with the given payload. Lets
// us cover flowStatusLine without mocking the client interface.
func statusFlowFixture(t *testing.T, body any, code int) *client.Client {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/signals/flow-windows/summary" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(code)
		_ = json.NewEncoder(w).Encode(body)
	}))
	t.Cleanup(srv.Close)
	return client.New(srv.URL, "test-token")
}

func TestFlowStatusLine_RendersCountAvgPeakWhenWindowsExist(t *testing.T) {
	c := statusFlowFixture(t, map[string]any{
		"count":        23,
		"avg":          0.67,
		"peak":         0.91,
		"peak_at":      "2026-05-01T14:32:00Z",
		"top_repo":     nil,
		"top_language": nil,
		"top_bundle":   nil,
	}, http.StatusOK)

	got := flowStatusLine(context.Background(), c)

	for _, want := range []string{"23 windows", "avg 67", "peak 91", "last hour"} {
		if !strings.Contains(got, want) {
			t.Errorf("expected status line to contain %q, got: %s", want, got)
		}
	}
}

func TestFlowStatusLine_EmptySliceShowsHelpfulHint(t *testing.T) {
	c := statusFlowFixture(t, map[string]any{
		"count":        0,
		"avg":          0,
		"peak":         0,
		"peak_at":      nil,
		"top_repo":     nil,
		"top_language": nil,
		"top_bundle":   nil,
	}, http.StatusOK)

	got := flowStatusLine(context.Background(), c)

	if !strings.Contains(got, "no windows in the last hour") {
		t.Errorf("expected empty-state hint, got: %s", got)
	}
}

// statusFlowFixtureRanged returns separate payloads depending on the
// width of the requested range — helper for the 1h-empty-but-24h-has-
// data fallback path. The handler infers which slice was requested by
// parsing the `start` query param relative to `end`.
func statusFlowFixtureRanged(t *testing.T, oneHour, twentyFourHour any) *client.Client {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/signals/flow-windows/summary" {
			http.NotFound(w, r)
			return
		}
		startStr := r.URL.Query().Get("start")
		endStr := r.URL.Query().Get("end")
		startT, _ := time.Parse(time.RFC3339, startStr)
		endT, _ := time.Parse(time.RFC3339, endStr)
		span := endT.Sub(startT)
		body := oneHour
		// Anything wider than ~6h is the 24h fallback. We use a loose
		// boundary so a few-second clock drift in the test doesn't tip
		// the response into the wrong branch.
		if span > 6*time.Hour {
			body = twentyFourHour
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(body)
	}))
	t.Cleanup(srv.Close)
	return client.New(srv.URL, "test-token")
}

func TestFlowStatusLine_FallsBackTo24hWhenLastHourIsEmpty(t *testing.T) {
	emptyBody := map[string]any{
		"count": 0, "avg": 0, "peak": 0, "peak_at": nil,
		"top_repo": nil, "top_language": nil, "top_bundle": nil,
	}
	dayBody := map[string]any{
		"count": 142, "avg": 0.55, "peak": 0.91, "peak_at": nil,
		"top_repo": nil, "top_language": nil, "top_bundle": nil,
	}
	c := statusFlowFixtureRanged(t, emptyBody, dayBody)

	got := flowStatusLine(context.Background(), c)

	// Disambiguates "broken pipeline" from "you just unsuspended" —
	// the 24h count shouldn't be hidden behind the 1h empty hint.
	if !strings.Contains(got, "no windows in the last hour") {
		t.Errorf("expected 1h hint, got: %s", got)
	}
	if !strings.Contains(got, "142 in last 24h") {
		t.Errorf("expected 24h fallback count, got: %s", got)
	}
}

func TestFlowStatusLine_ShowsBare1hHintWhen24hAlsoEmpty(t *testing.T) {
	// First-day-of-pairing case: nothing has accrued yet anywhere.
	// Don't render "no windows last hour · 0 in last 24h" — the
	// 0-suffix reads as redundant noise. Just the 1h hint.
	emptyBody := map[string]any{
		"count": 0, "avg": 0, "peak": 0, "peak_at": nil,
		"top_repo": nil, "top_language": nil, "top_bundle": nil,
	}
	c := statusFlowFixtureRanged(t, emptyBody, emptyBody)

	got := flowStatusLine(context.Background(), c)

	if got != "no windows in the last hour" {
		t.Errorf("expected bare 1h hint with no 24h suffix, got: %s", got)
	}
}

func TestFormatUptimeShort_Magnitudes(t *testing.T) {
	for _, c := range []struct {
		seconds int64
		want    string
	}{
		{0, "0s"},
		{42, "42s"},
		{60, "1m"},
		{3599, "59m"},
		{3600, "1h"},
		{86399, "23h"},
		{86400, "1d"},
		{86400 * 7, "7d"},
		{-12, "0s"}, // defensive: clock skew shouldn't render "-12s"
	} {
		if got := formatUptimeShort(c.seconds); got != c.want {
			t.Errorf("formatUptimeShort(%d) = %q, want %q", c.seconds, got, c.want)
		}
	}
}

func TestDaemonStatusDetail_ReadsHealthAndRendersCounts(t *testing.T) {
	// Stand up a fake /health endpoint on a free port and have
	// daemonStatusDetail probe it. Catches a regression in the
	// JSON parsing or the rendered string format.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/health" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"ok":              true,
			"version":         "test",
			"uptime_sec":      3661, // 1h 1min 1sec → "1h"
			"editor_count":    1,
			"windows_emitted": 142,
		})
	}))
	defer srv.Close()

	// Extract the port the test server bound to.
	port := portFromURL(t, srv.URL)
	got := daemonStatusDetail(port)

	// Lock in the prefix and the components — order matters for the
	// status line readability.
	for _, want := range []string{"running", "142 windows emitted", "uptime 1h"} {
		if !strings.Contains(got, want) {
			t.Errorf("expected detail to contain %q, got: %s", want, got)
		}
	}
}

func TestDaemonStatusDetail_FallsBackToPlainRunningOnError(t *testing.T) {
	// Probe a port nothing is bound to. daemonStatusDetail must NOT
	// hang or surface the error — just degrade to "running" so the
	// status command never wedges on an unreachable loopback.
	got := daemonStatusDetail(1) // port 1, not bindable by users; refused
	if got != "running" {
		t.Errorf("expected fallback to 'running' on probe failure, got: %s", got)
	}
}

// portFromURL extracts the port from an httptest.Server URL like
// "http://127.0.0.1:54321". Cheap helper kept here rather than a
// strconv chain at every callsite.
func portFromURL(t *testing.T, raw string) int {
	t.Helper()
	parsed, err := url.Parse(raw)
	if err != nil {
		t.Fatalf("parse %q: %v", raw, err)
	}
	port, err := strconv.Atoi(parsed.Port())
	if err != nil {
		t.Fatalf("port atoi %q: %v", parsed.Port(), err)
	}
	return port
}

func TestFlowStatusLine_ApiFailureReturnsSoftUnavailable(t *testing.T) {
	// Server returns 500 — flowStatusLine must NOT propagate the error
	// (status would partially succeed otherwise) and instead show a
	// soft "unavailable" message.
	c := statusFlowFixture(t, map[string]any{"detail": "boom"}, http.StatusInternalServerError)

	got := flowStatusLine(context.Background(), c)

	if got != "unavailable" {
		t.Errorf("expected 'unavailable' on API failure, got: %s", got)
	}
}

// --- formatStatusJSON / collectFlowStatus / renderFlowLine ---

func TestRenderFlowLine_HappyPath(t *testing.T) {
	got := renderFlowLine(flowStatus{
		WindowMinutes: 60, Available: true,
		Count: 23, Avg: 0.62, Peak: 0.91,
	})
	if got != "23 windows · avg 62 · peak 91 (last hour)" {
		t.Errorf("unexpected render: %q", got)
	}
}

func TestRenderFlowLine_UnavailableWhenNotAvailable(t *testing.T) {
	if got := renderFlowLine(flowStatus{}); got != "unavailable" {
		t.Errorf("expected 'unavailable' when Available is false, got %q", got)
	}
}

func TestRenderFlowLine_FallsBackTo24hCountWhenLastHourEmpty(t *testing.T) {
	got := renderFlowLine(flowStatus{
		WindowMinutes:    60,
		Available:        true,
		Count:            0,
		Count24hFallback: 47,
	})
	if got != "no windows in the last hour · 47 in last 24h" {
		t.Errorf("unexpected fallback render: %q", got)
	}
}

func TestRenderFlowLine_NoFallbackEitherShowsBareEmptyState(t *testing.T) {
	got := renderFlowLine(flowStatus{WindowMinutes: 60, Available: true})
	if got != "no windows in the last hour" {
		t.Errorf("unexpected empty-state render: %q", got)
	}
}

func TestFormatStatusJSON_RoundTrips(t *testing.T) {
	r := statusReport{
		Paired: true,
		Daemon: daemonStatus{Running: true, UptimeSec: 3600, WindowsEmitted: 60},
		API:    apiStatus{URL: "http://localhost:7999", Reachable: true},
		Timer:  timerStatus{Running: true, ProjectID: "p1", ProjectCategory: "coding"},
		Flow: flowStatus{
			WindowMinutes: 60, Available: true, Count: 23, Avg: 0.62, Peak: 0.91,
		},
	}
	out, err := formatStatusJSON(r)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.HasSuffix(out, "\n") {
		t.Errorf("expected trailing newline, got %q", out)
	}
	var decoded statusReport
	if err := json.Unmarshal([]byte(out), &decoded); err != nil {
		t.Fatalf("output should round-trip: %v", err)
	}
	if !decoded.Paired || !decoded.Daemon.Running || decoded.API.URL != "http://localhost:7999" {
		t.Errorf("decode wrong: %+v", decoded)
	}
	if decoded.Timer.ProjectID != "p1" || decoded.Timer.ProjectCategory != "coding" {
		t.Errorf("timer decode wrong: %+v", decoded.Timer)
	}
}

func TestFormatStatusJSON_ShapeIsStableOnFailurePath(t *testing.T) {
	// The whole point of the JSON form is that consumers can rely
	// on field presence regardless of which check failed. Pin the
	// "everything failed" shape — paired=false, daemon=zero,
	// api={url, reachable:false, error}, timer/flow at zero.
	r := statusReport{
		API:  apiStatus{URL: "http://localhost:7999", Error: "connection refused"},
		Flow: flowStatus{WindowMinutes: 60},
	}
	out, err := formatStatusJSON(r)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for _, want := range []string{
		`"paired": false`,
		`"running": false`,
		`"reachable": false`,
		`"error": "connection refused"`,
		`"available": false`,
	} {
		if !strings.Contains(out, want) {
			t.Errorf("expected %q in JSON, got: %s", want, out)
		}
	}
}

func TestFormatStatusJSON_OmitsErrorKeyOnSuccess(t *testing.T) {
	// Symmetric with doctor --json: the api.error key is
	// omitempty so jq's `select(.api.error)` finds failures
	// cleanly without having to filter empty strings.
	r := statusReport{
		Paired: true,
		API:    apiStatus{URL: "http://localhost:7999", Reachable: true},
		Flow:   flowStatus{WindowMinutes: 60, Available: true},
	}
	out, _ := formatStatusJSON(r)
	if strings.Contains(out, `"error"`) {
		t.Errorf("expected api.error to be omitted on success, got: %s", out)
	}
}

func TestCollectFlowStatus_HappyPath(t *testing.T) {
	c := statusFlowFixture(t, map[string]any{
		"count": 23, "avg": 0.62, "peak": 0.91, "peak_at": nil,
		"top_repo": nil, "top_language": nil, "top_bundle": nil,
	}, http.StatusOK)

	got := collectFlowStatus(context.Background(), c)
	if !got.Available || got.Count != 23 {
		t.Errorf("unexpected: %+v", got)
	}
	if got.Avg != 0.62 || got.Peak != 0.91 {
		t.Errorf("avg/peak wrong: %+v", got)
	}
}

func TestCollectFlowStatus_ApiFailureMarksUnavailable(t *testing.T) {
	c := statusFlowFixture(t, map[string]any{"detail": "boom"}, http.StatusInternalServerError)
	got := collectFlowStatus(context.Background(), c)
	if got.Available {
		t.Errorf("expected Available=false on API failure, got %+v", got)
	}
	if got.Count != 0 {
		t.Errorf("expected zero count on API failure, got %+v", got)
	}
}

// --- isStaleNoEmissions: cross-language parity with the VS Code
// extension's tooltip diagnostic ---

func TestIsStaleNoEmissions_FiresAtThreshold(t *testing.T) {
	// 90s matches the daemon's internal Accessibility re-probe
	// cadence; the VS Code extension's helper uses the same
	// threshold. Anything shorter would false-alarm during the
	// first window flush; anything longer would delay legitimate
	// diagnostics.
	if !isStaleNoEmissions(daemonStatus{Running: true, UptimeSec: 90, WindowsEmitted: 0}) {
		t.Error("expected stale at exactly 90s with 0 emissions")
	}
	if !isStaleNoEmissions(daemonStatus{Running: true, UptimeSec: 3600, WindowsEmitted: 0}) {
		t.Error("expected stale on a long-uptime daemon with 0 emissions")
	}
}

func TestIsStaleNoEmissions_DoesNotFireOnFreshDaemon(t *testing.T) {
	// 60s old, 0 emitted — the daemon hasn't had time to flush
	// even one window yet (windows are 60s each). False alarm.
	if isStaleNoEmissions(daemonStatus{Running: true, UptimeSec: 60, WindowsEmitted: 0}) {
		t.Error("expected no stale flag for freshly-started daemon")
	}
}

func TestIsStaleNoEmissions_DoesNotFireWhenWindowsEmitted(t *testing.T) {
	// Once any data has flowed, the pipeline is known-good. A long
	// quiet stretch (user not at the keyboard) shouldn't re-trigger
	// the diagnostic — that's not a system fault.
	if isStaleNoEmissions(daemonStatus{Running: true, UptimeSec: 3600, WindowsEmitted: 1}) {
		t.Error("expected no stale flag once any window has been emitted")
	}
}

func TestIsStaleNoEmissions_DoesNotFireWhenDaemonNotRunning(t *testing.T) {
	// If the daemon isn't running at all, the "not running" branch
	// of the human form already conveys the failure clearly. The
	// stale-no-emissions hint would just add noise on top.
	if isStaleNoEmissions(daemonStatus{Running: false, UptimeSec: 0, WindowsEmitted: 0}) {
		t.Error("expected no stale flag when the daemon is not running")
	}
}
