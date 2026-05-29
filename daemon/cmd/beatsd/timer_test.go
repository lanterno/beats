package main

import (
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
