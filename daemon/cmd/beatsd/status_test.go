package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
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
