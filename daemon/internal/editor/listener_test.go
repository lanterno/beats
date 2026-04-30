package editor

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
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
	listener := New()
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
	listener := New()
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
	listener := New()
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
	listener := New()
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
	listener := New()
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
	listener := New()
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
