// Package editor receives heartbeats from editor extensions (initially the
// VS Code extension at integrations/vscode-beats) so the collector can tag
// flow windows with the active workspace + branch.
//
// The listener binds to 127.0.0.1 only — the loopback interface is the
// entire trust boundary. Heartbeats carry workspace path + branch +
// language, never file content or keystrokes.
package editor

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net"
	"net/http"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// DefaultPort is the loopback TCP port the daemon binds for heartbeats.
// Configurable via EditorListenerConfig.Port.
const DefaultPort = 37499

// Heartbeat is a single beat from an editor. It always arrives with a
// timestamp from the editor's clock; the listener also stamps ReceivedAt
// from the daemon's clock for staleness checks.
type Heartbeat struct {
	Editor     string    `json:"editor"`
	Repo       string    `json:"repo,omitempty"`
	Branch     string    `json:"branch,omitempty"`
	Language   string    `json:"language,omitempty"`
	Timestamp  time.Time `json:"timestamp"`
	ReceivedAt time.Time `json:"-"`
}

// MaxStaleness is how long a heartbeat stays "current" before [Latest]
// reports nil. Editors typically beat every 30s; 90s gives us three
// missed beats of slack before we treat the editor as gone.
const MaxStaleness = 90 * time.Second

// SummaryFetcher fetches today's flow-window summary on behalf of an
// editor extension. Injected via [Listener.SetSummaryFetcher] so the
// editor package stays free of API-client imports — the daemon's main
// wires the real implementation; tests can pass a fake.
//
// The fetcher receives a context with a short deadline; implementations
// should respect it (loopback callers won't wait long).
type SummaryFetcher func(ctx context.Context) ([]byte, error)

// Listener accepts editor heartbeats on a loopback HTTP server and exposes
// the most recent beat per editor. Safe for concurrent use.
type Listener struct {
	mu             sync.Mutex
	heartbeats     map[string]Heartbeat // keyed by editor name
	server         *http.Server
	startedAt      time.Time
	version        string
	summaryFetcher SummaryFetcher
	windowsEmitted atomic.Int64 // updated by RecordWindowEmitted; surfaced on /health
}

// New constructs a listener. Call [Start] to bind the port; call [Latest]
// from any goroutine to read the most recent fresh heartbeat. The
// `version` string is surfaced verbatim on /health so editor UX can
// show e.g. "Beats: connected (v1.2.3)" — pass an empty string when
// the version isn't known.
func New(version string) *Listener {
	return &Listener{
		heartbeats: make(map[string]Heartbeat),
		startedAt:  time.Now(),
		version:    version,
	}
}

// SetSummaryFetcher wires up the fetcher used by GET /summary. Call
// before [Start] so the route is ready before the listener accepts
// connections. Without a fetcher /summary returns 503 Service
// Unavailable so editor extensions can fall back to the offline UI.
func (l *Listener) SetSummaryFetcher(fn SummaryFetcher) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.summaryFetcher = fn
}

// RecordWindowEmitted increments the per-process flow-window counter
// surfaced on /health. Called by the collector loop after a
// successful PostFlowWindow. Atomic so the listener's request
// handler can read it without holding the mutex.
func (l *Listener) RecordWindowEmitted() {
	l.windowsEmitted.Add(1)
}

// Start binds the listener to 127.0.0.1:port and begins accepting POST
// /heartbeat requests on a background goroutine. Returns once the listen
// socket is bound (or fails); the request loop runs until [Stop] is
// called or ctx is cancelled.
func (l *Listener) Start(ctx context.Context, port int) error {
	if port <= 0 {
		port = DefaultPort
	}

	addr := fmt.Sprintf("127.0.0.1:%d", port)
	listener, err := net.Listen("tcp", addr)
	if err != nil {
		return fmt.Errorf("editor: bind %s: %w", addr, err)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/heartbeat", l.handleHeartbeat)
	mux.HandleFunc("/health", l.handleHealth)
	mux.HandleFunc("/summary", l.handleSummary)

	l.server = &http.Server{
		Handler:           mux,
		ReadHeaderTimeout: 2 * time.Second,
		ReadTimeout:       5 * time.Second,
		WriteTimeout:      5 * time.Second,
	}

	go func() {
		log.Printf("editor: listening on %s for editor heartbeats", addr)
		if err := l.server.Serve(listener); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Printf("editor: serve error: %v", err)
		}
	}()

	go func() {
		<-ctx.Done()
		_ = l.Stop()
	}()

	return nil
}

// Stop gracefully shuts the listener down. Safe to call multiple times.
func (l *Listener) Stop() error {
	if l.server == nil {
		return nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	return l.server.Shutdown(ctx)
}

// Latest returns the most recently received heartbeat across all editors,
// provided it's fresher than [MaxStaleness]. Returns nil if no editor has
// sent anything recently.
func (l *Listener) Latest() *Heartbeat {
	l.mu.Lock()
	defer l.mu.Unlock()
	now := time.Now()
	var newest *Heartbeat
	for _, hb := range l.heartbeats {
		if now.Sub(hb.ReceivedAt) > MaxStaleness {
			continue
		}
		if newest == nil || hb.ReceivedAt.After(newest.ReceivedAt) {
			b := hb
			newest = &b
		}
	}
	return newest
}

// All returns a snapshot of every fresh heartbeat keyed by editor name.
// Useful when more than one editor (e.g. VS Code + a JetBrains IDE) is
// open at once and the caller wants to disambiguate.
func (l *Listener) All() map[string]Heartbeat {
	l.mu.Lock()
	defer l.mu.Unlock()
	now := time.Now()
	out := make(map[string]Heartbeat, len(l.heartbeats))
	for k, hb := range l.heartbeats {
		if now.Sub(hb.ReceivedAt) <= MaxStaleness {
			out[k] = hb
		}
	}
	return out
}

// HealthResponse is the public shape of GET /health on the editor
// listener. Designed for editor extensions to probe in a setInterval —
// JSON tag names are stable and snake_case to match the rest of the
// API surface. `editor_count` reports how many distinct editors have
// sent at least one fresh heartbeat (≤ MaxStaleness old);
// `windows_emitted` reports how many flow windows this daemon process
// has POSTed since startup (proxy for "is the collector actually
// producing?").
type HealthResponse struct {
	OK             bool   `json:"ok"`
	Version        string `json:"version"`
	UptimeSec      int64  `json:"uptime_sec"`
	EditorCount    int    `json:"editor_count"`
	WindowsEmitted int64  `json:"windows_emitted"`
}

// handleHealth serves a tiny status snapshot so editor extensions can
// probe whether the daemon is running and ready to accept heartbeats.
// Same loopback-only enforcement as /heartbeat. GET-only.
func (l *Listener) handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil || !isLoopback(host) {
		http.Error(w, "forbidden", http.StatusForbidden)
		return
	}

	resp := HealthResponse{
		OK:             true,
		Version:        l.version,
		UptimeSec:      int64(time.Since(l.startedAt).Seconds()),
		EditorCount:    len(l.All()),
		WindowsEmitted: l.windowsEmitted.Load(),
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(resp)
}

// handleSummary proxies GET /api/signals/flow-windows/summary on
// behalf of editor extensions. The daemon already authenticates with
// the API via the keychain device token, so editors don't need their
// own auth — they just hit this loopback URL.
//
// Returns the API response body verbatim (the schema is stable; we
// don't massage it). On no-fetcher-configured we 503 so the editor
// can keep its UI in the offline state. On fetcher error we propagate
// 502 — the daemon is up but the upstream call failed.
func (l *Listener) handleSummary(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil || !isLoopback(host) {
		http.Error(w, "forbidden", http.StatusForbidden)
		return
	}

	l.mu.Lock()
	fetch := l.summaryFetcher
	l.mu.Unlock()
	if fetch == nil {
		http.Error(w, "summary fetcher not configured", http.StatusServiceUnavailable)
		return
	}

	// Cap the upstream call at 3s — editors poll on a tight cadence
	// and a stuck request shouldn't wedge the status bar.
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()
	body, err := fetch(ctx)
	if err != nil {
		http.Error(w, "upstream summary fetch failed", http.StatusBadGateway)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write(body)
}

func (l *Listener) handleHeartbeat(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Only accept loopback peers. RemoteAddr is "ip:port" — strip the port.
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil || !isLoopback(host) {
		http.Error(w, "forbidden", http.StatusForbidden)
		return
	}

	// Cap body size to defend against a misbehaving editor / random client.
	r.Body = http.MaxBytesReader(w, r.Body, 4*1024)
	defer r.Body.Close()

	var hb Heartbeat
	if err := json.NewDecoder(r.Body).Decode(&hb); err != nil {
		http.Error(w, "bad json", http.StatusBadRequest)
		return
	}
	if strings.TrimSpace(hb.Editor) == "" {
		http.Error(w, "missing editor", http.StatusBadRequest)
		return
	}
	hb.ReceivedAt = time.Now()

	l.mu.Lock()
	l.heartbeats[hb.Editor] = hb
	l.mu.Unlock()

	w.WriteHeader(http.StatusNoContent)
}

func isLoopback(host string) bool {
	if host == "127.0.0.1" || host == "::1" || host == "localhost" {
		return true
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}
