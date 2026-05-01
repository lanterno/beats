package main

import (
	"encoding/json"
	"net"
	"net/http"
	"net/http/httptest"
	"runtime"
	"strings"
	"testing"

	"github.com/ahmedElghable/beats/daemon/internal/client"
	"github.com/ahmedElghable/beats/daemon/internal/editor"
)

func TestCheckEditorPort_OK(t *testing.T) {
	// Best-effort happy path — assumes nothing else is bound to the
	// default port at test time. If a parallel test or another beatsd
	// is running we'll skip rather than fail (this isn't the contract
	// we're testing here).
	if isDefaultPortInUse() {
		t.Skip("default editor port already in use; skipping happy path")
	}
	detail, err := checkEditorPort()
	if err != nil {
		t.Errorf("expected nil error when port is free, got %v", err)
	}
	if !strings.Contains(detail, "available") {
		t.Errorf("expected detail to mention availability, got %q", detail)
	}
}

func TestCheckEditorPort_FailsWhenPortAlreadyBound(t *testing.T) {
	// Bind the listener ourselves, then call the doctor check. It
	// should detect the conflict and return an error pointing at the
	// "another beatsd already running" possibility.
	addr := net.JoinHostPort("127.0.0.1", portString(editor.DefaultPort))
	l, err := net.Listen("tcp", addr)
	if err != nil {
		t.Skipf("could not bind %s ourselves: %v", addr, err)
	}
	defer l.Close()

	_, gotErr := checkEditorPort()
	if gotErr == nil {
		t.Fatal("expected an error when port is in use, got nil")
	}
	if !strings.Contains(gotErr.Error(), "in use") {
		t.Errorf("expected 'in use' in error, got %q", gotErr.Error())
	}
}

func TestCheckEventTap_NonDarwinFallsBackInformatively(t *testing.T) {
	// Linux / Windows runners hit the stub, which should report
	// "stub fallback" with NO error — informational, not a failure
	// (cadence just defaults to 0.5).
	if runtime.GOOS == "darwin" {
		t.Skip("happy/sad paths on darwin depend on Accessibility permission")
	}
	detail, err := checkEventTap()
	if err != nil {
		t.Errorf("non-darwin should not surface an error, got %v", err)
	}
	if !strings.Contains(detail, "stub fallback") {
		t.Errorf("expected stub-fallback detail, got %q", detail)
	}
}

// --- flowDataDetail ---

// summaryFixture stands up an httptest server that responds to
// /api/signals/flow-windows/summary with the given JSON payload + status.
// Returns a wired Client so the doctor function can be exercised without
// touching the keychain or hitting the real API.
func summaryFixture(t *testing.T, body any, code int) *client.Client {
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

func TestFlowDataDetail_RendersCountAndAvgWhenWindowsExist(t *testing.T) {
	c := summaryFixture(t, map[string]any{
		"count": 47, "avg": 0.62, "peak": 0.84, "peak_at": nil,
		"top_repo": nil, "top_language": nil, "top_bundle": nil,
	}, http.StatusOK)

	got := flowDataDetail(c)

	for _, want := range []string{"47 windows", "avg 62", "last hour"} {
		if !strings.Contains(got, want) {
			t.Errorf("expected detail to contain %q, got: %s", want, got)
		}
	}
}

func TestFlowDataDetail_EmptySliceMentionsBeatsdRun(t *testing.T) {
	// The hint "(start `beatsd run` if not already running)" is the
	// actionable nudge — locked in so a refactor doesn't strip it.
	c := summaryFixture(t, map[string]any{
		"count": 0, "avg": 0, "peak": 0, "peak_at": nil,
		"top_repo": nil, "top_language": nil, "top_bundle": nil,
	}, http.StatusOK)

	got := flowDataDetail(c)

	if !strings.Contains(got, "no windows in the last hour") {
		t.Errorf("expected empty-state hint, got: %s", got)
	}
	if !strings.Contains(got, "beatsd run") {
		t.Errorf("expected actionable suggestion, got: %s", got)
	}
}

func TestFlowDataDetail_ApiFailureReturnsSoftMessage(t *testing.T) {
	// API outage / token revoked — must NOT propagate the error
	// (doctor would partially succeed otherwise) and instead show
	// a soft "summary fetch failed" detail. The user-facing check
	// stays in the ✓ column because doctor's contract is "validate
	// setup", not "validate live data".
	c := summaryFixture(t, map[string]any{"detail": "boom"}, http.StatusInternalServerError)

	got := flowDataDetail(c)

	if got != "summary fetch failed" {
		t.Errorf("expected 'summary fetch failed' on API error, got: %s", got)
	}
}

// --- helpers ---

func isDefaultPortInUse() bool {
	addr := net.JoinHostPort("127.0.0.1", portString(editor.DefaultPort))
	l, err := net.Listen("tcp", addr)
	if err != nil {
		return true
	}
	_ = l.Close()
	return false
}

func portString(p int) string {
	// Tiny inline strconv to avoid pulling fmt/strconv into the test
	// file just for one int → string. Not worth the dep weight.
	if p == 0 {
		return "0"
	}
	digits := []byte{}
	for n := p; n > 0; n /= 10 {
		digits = append([]byte{byte('0' + n%10)}, digits...)
	}
	return string(digits)
}
