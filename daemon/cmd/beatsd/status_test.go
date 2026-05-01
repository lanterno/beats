package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

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
