package editor

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"testing"
	"time"
)

// freePort returns an unused TCP port on 127.0.0.1 by asking the OS for one.
// The socket is closed before returning so the test can re-bind it.
func freePort(t *testing.T) int {
	t.Helper()
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("freePort: %v", err)
	}
	port := l.Addr().(*net.TCPAddr).Port
	_ = l.Close()
	return port
}

func postHeartbeat(t *testing.T, port int, hb Heartbeat) *http.Response {
	t.Helper()
	body, _ := json.Marshal(hb)
	resp, err := http.Post(
		fmt.Sprintf("http://127.0.0.1:%d/heartbeat", port),
		"application/json",
		bytes.NewReader(body),
	)
	if err != nil {
		t.Fatalf("POST: %v", err)
	}
	return resp
}

func TestListener_AcceptsAndExposesHeartbeat(t *testing.T) {
	listener := New("test-version")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	port := freePort(t)
	if err := listener.Start(ctx, port); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer func() { _ = listener.Stop() }()

	hb := Heartbeat{
		Editor:    "vscode",
		Repo:      "/Users/me/code/example",
		Branch:    "main",
		Language:  "go",
		Timestamp: time.Now().UTC(),
	}
	resp := postHeartbeat(t, port, hb)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusNoContent {
		t.Fatalf("status: got %d, want %d", resp.StatusCode, http.StatusNoContent)
	}

	got := listener.Latest()
	if got == nil {
		t.Fatal("Latest returned nil after heartbeat")
	}
	if got.Editor != "vscode" || got.Repo != hb.Repo || got.Branch != "main" {
		t.Errorf("unexpected heartbeat: %+v", got)
	}
	if got.ReceivedAt.IsZero() {
		t.Error("ReceivedAt should be stamped on receive")
	}
}

func TestListener_RejectsNonPost(t *testing.T) {
	listener := New("test-version")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	port := freePort(t)
	if err := listener.Start(ctx, port); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer func() { _ = listener.Stop() }()

	resp, err := http.Get(fmt.Sprintf("http://127.0.0.1:%d/heartbeat", port))
	if err != nil {
		t.Fatalf("GET: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Errorf("got %d, want 405", resp.StatusCode)
	}
}

func TestListener_RejectsBadJSON(t *testing.T) {
	listener := New("test-version")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	port := freePort(t)
	if err := listener.Start(ctx, port); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer func() { _ = listener.Stop() }()

	resp, err := http.Post(
		fmt.Sprintf("http://127.0.0.1:%d/heartbeat", port),
		"application/json",
		bytes.NewBufferString("not json"),
	)
	if err != nil {
		t.Fatalf("POST: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("got %d, want 400", resp.StatusCode)
	}
}

func TestListener_RejectsMissingEditor(t *testing.T) {
	listener := New("test-version")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	port := freePort(t)
	if err := listener.Start(ctx, port); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer func() { _ = listener.Stop() }()

	resp := postHeartbeat(t, port, Heartbeat{Repo: "/x", Timestamp: time.Now()})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("got %d, want 400", resp.StatusCode)
	}
}

func TestListener_LatestPicksMostRecentEditor(t *testing.T) {
	listener := New("test-version")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	port := freePort(t)
	if err := listener.Start(ctx, port); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer func() { _ = listener.Stop() }()

	postHeartbeat(t, port, Heartbeat{Editor: "vscode", Repo: "/a", Timestamp: time.Now()}).Body.Close()
	time.Sleep(5 * time.Millisecond)
	postHeartbeat(t, port, Heartbeat{Editor: "jetbrains", Repo: "/b", Timestamp: time.Now()}).Body.Close()

	got := listener.Latest()
	if got == nil || got.Editor != "jetbrains" {
		t.Fatalf("expected most-recent editor jetbrains, got %+v", got)
	}

	all := listener.All()
	if len(all) != 2 {
		t.Errorf("expected 2 fresh editors, got %d", len(all))
	}
}

func TestListener_StaleEntriesAreSkipped(t *testing.T) {
	listener := New("test-version")
	// Build the heartbeat directly so we can predate ReceivedAt past
	// MaxStaleness without sleeping for 90s.
	listener.heartbeats["vscode"] = Heartbeat{
		Editor:     "vscode",
		Repo:       "/x",
		ReceivedAt: time.Now().Add(-2 * MaxStaleness),
	}
	if listener.Latest() != nil {
		t.Error("stale heartbeat should not surface from Latest()")
	}
	if len(listener.All()) != 0 {
		t.Error("stale heartbeat should not appear in All()")
	}
}

func TestListener_HealthEndpointReportsStatus(t *testing.T) {
	listener := New("v1.2.3-test")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	port := freePort(t)
	if err := listener.Start(ctx, port); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer func() { _ = listener.Stop() }()

	// Post a heartbeat first so editor_count > 0 in the response.
	postResp := postHeartbeat(t, port, Heartbeat{
		Editor: "vscode", Timestamp: time.Now().UTC(),
	})
	postResp.Body.Close()

	resp, err := http.Get(fmt.Sprintf("http://127.0.0.1:%d/health", port))
	if err != nil {
		t.Fatalf("GET /health: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", resp.StatusCode)
	}

	var got HealthResponse
	if err := json.NewDecoder(resp.Body).Decode(&got); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if !got.OK {
		t.Errorf("expected ok=true, got %+v", got)
	}
	if got.Version != "v1.2.3-test" {
		t.Errorf("expected version 'v1.2.3-test' verbatim, got %q", got.Version)
	}
	if got.UptimeSec < 0 {
		t.Errorf("uptime should be non-negative, got %d", got.UptimeSec)
	}
	if got.EditorCount != 1 {
		t.Errorf("expected editor_count=1 after one heartbeat, got %d", got.EditorCount)
	}
}

func TestListener_SummaryReturnsFetcherBytesVerbatim(t *testing.T) {
	listener := New("test")
	listener.SetSummaryFetcher(func(_ context.Context) ([]byte, error) {
		// Fixture body — keep it identifiable so we can assert
		// pass-through without parsing.
		return []byte(`{"count":42,"avg":0.67}`), nil
	})

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	port := freePort(t)
	if err := listener.Start(ctx, port); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer func() { _ = listener.Stop() }()

	resp, err := http.Get(fmt.Sprintf("http://127.0.0.1:%d/summary", port))
	if err != nil {
		t.Fatalf("GET /summary: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", resp.StatusCode)
	}
	if ct := resp.Header.Get("Content-Type"); ct != "application/json" {
		t.Errorf("expected application/json, got %q", ct)
	}
	body, _ := io.ReadAll(resp.Body)
	if string(body) != `{"count":42,"avg":0.67}` {
		t.Errorf("expected fetcher bytes verbatim, got %s", body)
	}
}

func TestListener_SummaryReturns503WhenNoFetcherWired(t *testing.T) {
	// The fetcher is wired by main.go — but a daemon binary that
	// fails to authenticate (or runs in dry-mode) might not call
	// SetSummaryFetcher. The endpoint should 503 cleanly so the
	// editor can keep its UI in the offline state rather than 500'ing.
	listener := New("test")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	port := freePort(t)
	if err := listener.Start(ctx, port); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer func() { _ = listener.Stop() }()

	resp, err := http.Get(fmt.Sprintf("http://127.0.0.1:%d/summary", port))
	if err != nil {
		t.Fatalf("GET /summary: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusServiceUnavailable {
		t.Errorf("expected 503, got %d", resp.StatusCode)
	}
}

func TestListener_SummaryReturns502OnFetcherError(t *testing.T) {
	// API outage / token revoked / network blip — the fetcher errors,
	// the daemon proxy translates to 502 (upstream gateway problem)
	// instead of 500. The editor's status bar should treat that as
	// "connected but no data" rather than "daemon dead".
	listener := New("test")
	listener.SetSummaryFetcher(func(_ context.Context) ([]byte, error) {
		return nil, errors.New("upstream is on fire")
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	port := freePort(t)
	if err := listener.Start(ctx, port); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer func() { _ = listener.Stop() }()

	resp, err := http.Get(fmt.Sprintf("http://127.0.0.1:%d/summary", port))
	if err != nil {
		t.Fatalf("GET /summary: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadGateway {
		t.Errorf("expected 502, got %d", resp.StatusCode)
	}
}

func TestListener_SummaryRejectsNonGet(t *testing.T) {
	listener := New("test")
	listener.SetSummaryFetcher(func(_ context.Context) ([]byte, error) {
		return []byte(`{}`), nil
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	port := freePort(t)
	if err := listener.Start(ctx, port); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer func() { _ = listener.Stop() }()

	resp, err := http.Post(
		fmt.Sprintf("http://127.0.0.1:%d/summary", port),
		"application/json",
		bytes.NewReader([]byte("{}")),
	)
	if err != nil {
		t.Fatalf("POST: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Errorf("expected 405, got %d", resp.StatusCode)
	}
}

func TestListener_HealthRejectsNonGet(t *testing.T) {
	// Method-allowed for /health is GET only — POST should 405.
	// Mirror the same hygiene as /heartbeat which is POST-only.
	listener := New("test-version")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	port := freePort(t)
	if err := listener.Start(ctx, port); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer func() { _ = listener.Stop() }()

	resp, err := http.Post(
		fmt.Sprintf("http://127.0.0.1:%d/health", port),
		"application/json",
		bytes.NewReader([]byte("{}")),
	)
	if err != nil {
		t.Fatalf("POST: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Errorf("expected 405 on POST /health, got %d", resp.StatusCode)
	}
}
