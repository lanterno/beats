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

// Listener accepts editor heartbeats on a loopback HTTP server and exposes
// the most recent beat per editor. Safe for concurrent use.
type Listener struct {
	mu         sync.Mutex
	heartbeats map[string]Heartbeat // keyed by editor name
	server     *http.Server
}

// New constructs a listener. Call [Start] to bind the port; call [Latest]
// from any goroutine to read the most recent fresh heartbeat.
func New() *Listener {
	return &Listener{heartbeats: make(map[string]Heartbeat)}
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
