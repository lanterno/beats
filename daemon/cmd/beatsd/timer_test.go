package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/client"
)

func sampleProjects() []client.Project {
	return []client.Project{
		{ID: "1", Name: "Linear"},
		{ID: "2", Name: "Beats API"},
		{ID: "3", Name: "Beats UI"},
		{ID: "4", Name: "Archived One", Archived: true},
	}
}

func TestParseStartArgs(t *testing.T) {
	tests := []struct {
		name string
		args []string
		hint string
		json bool
	}{
		{"single token", []string{"linear"}, "linear", false},
		{"multi-word hint joins with space", []string{"side", "project"}, "side project", false},
		{"json flag at end", []string{"linear", "--json"}, "linear", true},
		{"json flag first", []string{"--json", "beats", "api"}, "beats api", true},
		{"empty", []string{}, "", false},
		{"only json", []string{"--json"}, "", true},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			h, j := parseStartArgs(tc.args)
			if h != tc.hint {
				t.Errorf("hint: got %q want %q", h, tc.hint)
			}
			if j != tc.json {
				t.Errorf("json: got %v want %v", j, tc.json)
			}
		})
	}
}

func TestResolveProject(t *testing.T) {
	mustMatch := func(t *testing.T, hint, wantID string) {
		t.Helper()
		p, err := resolveProject(hint, sampleProjects())
		if err != nil {
			t.Fatalf("%q: unexpected error: %v", hint, err)
		}
		if p.ID != wantID {
			t.Errorf("%q: got id %s want %s", hint, p.ID, wantID)
		}
	}
	mustErr := func(t *testing.T, hint string) {
		t.Helper()
		if _, err := resolveProject(hint, sampleProjects()); err == nil {
			t.Fatalf("%q: expected error", hint)
		}
	}

	t.Run("exact case-insensitive", func(t *testing.T) { mustMatch(t, "linear", "1") })
	t.Run("exact wins over prefix ambiguity", func(t *testing.T) { mustMatch(t, "beats api", "2") })
	t.Run("unique prefix", func(t *testing.T) { mustMatch(t, "lin", "1") })
	t.Run("unique substring", func(t *testing.T) { mustMatch(t, "api", "2") })
	t.Run("ambiguous prefix errors", func(t *testing.T) { mustErr(t, "beats") })
	t.Run("no match errors", func(t *testing.T) { mustErr(t, "zzz") })
	t.Run("empty hint errors", func(t *testing.T) { mustErr(t, "   ") })
	t.Run("archived projects are ignored", func(t *testing.T) { mustErr(t, "archived") })

	t.Run("no active projects errors", func(t *testing.T) {
		_, err := resolveProject("x", []client.Project{{ID: "9", Name: "Gone", Archived: true}})
		if err == nil {
			t.Fatal("expected error when no active projects")
		}
	})
	t.Run("ambiguous error lists candidates", func(t *testing.T) {
		_, err := resolveProject("beats", sampleProjects())
		if err == nil || !strings.Contains(err.Error(), "Beats API") || !strings.Contains(err.Error(), "Beats UI") {
			t.Errorf("expected candidate list in error, got %v", err)
		}
	})
}

func TestFormatStartResult(t *testing.T) {
	p := client.Project{ID: "1", Name: "Linear"}
	if got := formatStartResult(p, false); got != "Started Linear" {
		t.Errorf("text: got %q", got)
	}
	got := formatStartResult(p, true)
	if !strings.Contains(got, `"action":"start"`) ||
		!strings.Contains(got, `"project_id":"1"`) ||
		!strings.Contains(got, `"project_name":"Linear"`) {
		t.Errorf("json missing fields: %s", got)
	}
}

func TestBeatMinutes(t *testing.T) {
	start := time.Date(2026, 5, 29, 10, 0, 0, 0, time.UTC)
	if got := beatMinutes(&client.StoppedBeat{Start: start, End: start.Add(42 * time.Minute)}); got != 42 {
		t.Errorf("42m span: got %d", got)
	}
	if got := beatMinutes(&client.StoppedBeat{Start: start, End: start.Add(-time.Minute)}); got != 0 {
		t.Errorf("negative span should clamp to 0, got %d", got)
	}
	if got := beatMinutes(nil); got != 0 {
		t.Errorf("nil should be 0, got %d", got)
	}
	if got := beatMinutes(&client.StoppedBeat{}); got != 0 {
		t.Errorf("zero-value should be 0, got %d", got)
	}
}

func TestFormatStopResult(t *testing.T) {
	start := time.Date(2026, 5, 29, 10, 0, 0, 0, time.UTC)
	b := &client.StoppedBeat{ProjectID: "p1", Start: start, End: start.Add(90 * time.Minute)}
	if got := formatStopResult(b, false); got != "Stopped — logged 90m" {
		t.Errorf("text: got %q", got)
	}
	got := formatStopResult(b, true)
	if !strings.Contains(got, `"action":"stop"`) || !strings.Contains(got, `"duration_minutes":90`) {
		t.Errorf("json missing fields: %s", got)
	}
}

// --- note ---

// The same cases as appendToNote's in companion/test/timer_controller_test.dart:
// one rule, two implementations.
func TestAppendNote(t *testing.T) {
	tests := []struct{ existing, text, want string }{
		// A first line is the note.
		{"", "called Ana", "called Ana"},
		{"  ", " called Ana ", "called Ana"},
		// It stays on the one line a note is.
		{"Sprint review", "called Ana", "Sprint review; called Ana"},
		{"Sprint review.", "Called Ana", "Sprint review. Called Ana"},
		{"Sprint review", "called\nAna", "Sprint review; called Ana"},
		// An empty line leaves the note as it was.
		{"Sprint review", "   ", "Sprint review"},
	}
	for _, tc := range tests {
		if got := appendNote(tc.existing, tc.text); got != tc.want {
			t.Errorf("appendNote(%q, %q) = %q, want %q", tc.existing, tc.text, got, tc.want)
		}
	}
}

// noteAPI is the three calls `note` makes: the timer status, the running
// project's sessions on a day, and the write. puts records each write's body.
type noteAPI struct {
	status string
	beats  string
	put    func(w http.ResponseWriter)
	puts   []map[string]any
}

func (a *noteAPI) serve(t *testing.T) *client.Client {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/timer/status":
			fmt.Fprint(w, a.status)
		case r.Method == http.MethodGet && r.URL.Path == "/api/beats/":
			fmt.Fprint(w, a.beats)
		case r.Method == http.MethodPut && r.URL.Path == "/api/beats/":
			var body map[string]any
			_ = json.NewDecoder(r.Body).Decode(&body)
			a.puts = append(a.puts, body)
			if a.put != nil {
				a.put(w)
				return
			}
			fmt.Fprint(w, `{}`)
		default:
			t.Errorf("unexpected %s %s", r.Method, r.URL)
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	t.Cleanup(srv.Close)
	return client.New(srv.URL, "tok")
}

const runningKite = `{"isBeating": true, "since": "2026-11-16T08:00:00.250000Z",
	"project": {"id": "p1", "name": "Kite", "archived": false, "organisation": null}}`

func TestAddToNote_WritesTheRunningSessionAsItWasRead(t *testing.T) {
	api := &noteAPI{
		status: runningKite,
		// The morning's finished session comes first; the one without an end runs.
		beats: `[
			{"id": "b0", "project_id": "p1", "start": "2026-11-16T06:00:00Z", "end": "2026-11-16T07:00:00Z", "note": "earlier"},
			{"id": "b1", "project_id": "p1", "start": "2026-11-16T08:00:00.250000Z", "end": null, "note": "Sprint review"}
		]`,
	}
	n, err := addToNote(context.Background(), api.serve(t), "called Ana")
	if err != nil {
		t.Fatalf("addToNote: %v", err)
	}
	if n.note != "Sprint review; called Ana" || n.project.Name != "Kite" {
		t.Errorf("got %+v", n)
	}
	if len(api.puts) != 1 {
		t.Fatalf("expected one write, got %d", len(api.puts))
	}
	put := api.puts[0]
	if put["id"] != "b1" || put["note"] != "Sprint review; called Ana" || put["end"] != nil {
		t.Errorf("write: %v", put)
	}
	// The API compares the instant exactly, fraction of a second included.
	expected, _ := put["expected"].(map[string]any)
	if expected["project_id"] != "p1" || expected["start"] != "2026-11-16T08:00:00.25Z" || expected["end"] != nil {
		t.Errorf("expected: %v", expected)
	}
}

func TestAddToNote_RefusesWithoutWriting(t *testing.T) {
	long := strings.Repeat("€", 1990) // 1990 characters, 5970 bytes
	tests := []struct {
		name    string
		api     *noteAPI
		text    string
		wantErr string
	}{
		{
			name:    "nothing running",
			api:     &noteAPI{status: `{"isBeating": false, "last_beat": {"id": "b0", "project_id": "p1", "end": "2026-11-16T07:00:00Z"}}`},
			text:    "called Ana",
			wantErr: "nothing is running",
		},
		{
			name:    "the running session is not on its day",
			api:     &noteAPI{status: runningKite, beats: `[]`},
			text:    "called Ana",
			wantErr: "not found",
		},
		{
			name: "past the limit",
			api: &noteAPI{status: runningKite, beats: `[{"id": "b1", "project_id": "p1",
				"start": "2026-11-16T08:00:00Z", "end": null, "note": "` + long + `"}]`},
			text:    "called Ana", // "; called Ana" makes 2002
			wantErr: "past 2000 characters",
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			_, err := addToNote(context.Background(), tc.api.serve(t), tc.text)
			if err == nil || !strings.Contains(err.Error(), tc.wantErr) {
				t.Errorf("got %v, want an error containing %q", err, tc.wantErr)
			}
			if len(tc.api.puts) != 0 {
				t.Errorf("wrote %v", tc.api.puts)
			}
		})
	}
}

func TestAddToNote_CountsCharactersNotBytes(t *testing.T) {
	// 1988 euro signs and "; called Ana" are 2000 characters, the most a
	// note holds, though nearly three times as many bytes.
	api := &noteAPI{status: runningKite, beats: `[{"id": "b1", "project_id": "p1",
		"start": "2026-11-16T08:00:00Z", "end": null, "note": "` + strings.Repeat("€", 1988) + `"}]`}
	if _, err := addToNote(context.Background(), api.serve(t), "called Ana"); err != nil {
		t.Fatalf("a note of exactly 2000 characters was refused: %v", err)
	}
	if len(api.puts) != 1 {
		t.Errorf("expected one write, got %d", len(api.puts))
	}
}

func TestAddToNote_ASessionChangedElsewhereIsSaidSo(t *testing.T) {
	api := &noteAPI{
		status: runningKite,
		beats:  `[{"id": "b1", "project_id": "p1", "start": "2026-11-16T08:00:00Z", "end": null, "note": null}]`,
		put: func(w http.ResponseWriter) {
			w.WriteHeader(http.StatusConflict)
			fmt.Fprint(w, `{"detail": "The session changed", "code": "BEAT_CHANGED"}`)
		},
	}
	_, err := addToNote(context.Background(), api.serve(t), "called Ana")
	if err == nil || !strings.Contains(err.Error(), "another device") {
		t.Errorf("got %v", err)
	}
}

func TestFormatNoteResult_SaysWhoReadsTheNote(t *testing.T) {
	kite := client.Project{ID: "p1", Name: "Kite"}
	acme := client.Project{ID: "p2", Name: "Payroll", Organisation: &client.ProjectOrganisation{Name: "Acme"}}

	if got := formatNoteResult(noted{project: kite, note: "x"}, false); got != "Added to the note on Kite" {
		t.Errorf("personal: %q", got)
	}
	if got := formatNoteResult(noted{project: acme, note: "x"}, false); got != "Added to the note on Payroll — Acme can read this note" {
		t.Errorf("organisation's: %q", got)
	}

	var out map[string]any
	if err := json.Unmarshal([]byte(formatNoteResult(noted{project: kite, note: "a; b"}, true)), &out); err != nil {
		t.Fatal(err)
	}
	if out["action"] != "note" || out["note"] != "a; b" || out["organisation"] != nil {
		t.Errorf("personal JSON: %v", out)
	}
	if err := json.Unmarshal([]byte(formatNoteResult(noted{project: acme}, true)), &out); err != nil {
		t.Fatal(err)
	}
	if out["organisation"] != "Acme" {
		t.Errorf("organisation's JSON: %v", out)
	}
}
