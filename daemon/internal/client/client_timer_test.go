package client

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestGetProjects(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Errorf("expected GET, got %s", r.Method)
		}
		if r.URL.Path != "/api/projects/" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		if r.Header.Get("Authorization") != "Bearer tok" {
			t.Errorf("missing/wrong auth: %s", r.Header.Get("Authorization"))
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`[{"id":"p1","name":"Alpha","archived":false},{"id":"p2","name":"Old","archived":true}]`))
	}))
	defer srv.Close()

	c := New(srv.URL, "tok")
	ps, err := c.GetProjects(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(ps) != 2 {
		t.Fatalf("expected 2 projects, got %d", len(ps))
	}
	if ps[0].ID != "p1" || ps[0].Name != "Alpha" || ps[0].Archived {
		t.Errorf("bad first project: %+v", ps[0])
	}
	if !ps[1].Archived {
		t.Errorf("expected p2 archived")
	}
}

func TestGetProjectsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte(`{"detail":"boom","code":"X"}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "tok")
	if _, err := c.GetProjects(context.Background()); err == nil {
		t.Fatal("expected error on 500")
	}
}

func TestStartTimer(t *testing.T) {
	var gotMethod, gotPath, gotAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod, gotPath, gotAuth = r.Method, r.URL.Path, r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"id":"b1","project_id":"p1"}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "tok")
	if err := c.StartTimer(context.Background(), "p1"); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if gotMethod != http.MethodPost {
		t.Errorf("expected POST, got %s", gotMethod)
	}
	if gotPath != "/api/projects/p1/start" {
		t.Errorf("unexpected path: %s", gotPath)
	}
	if gotAuth != "Bearer tok" {
		t.Errorf("missing auth: %s", gotAuth)
	}
}

func TestStartTimerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusConflict)
		w.Write([]byte(`{"detail":"already running","code":"TIMER_RUNNING"}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "tok")
	if err := c.StartTimer(context.Background(), "p1"); err == nil {
		t.Fatal("expected error on 409")
	}
}

func TestStopTimer(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		if r.URL.Path != "/api/projects/stop" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"project_id":"p1","start":"2026-05-29T10:00:00Z","end":"2026-05-29T10:42:00Z"}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "tok")
	b, err := c.StopTimer(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if b.ProjectID != "p1" {
		t.Errorf("expected p1, got %s", b.ProjectID)
	}
	if got := b.End.Sub(b.Start); got != 42*time.Minute {
		t.Errorf("expected 42m span, got %v", got)
	}
}

func TestStopTimerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		w.Write([]byte(`{"detail":"no timer running","code":"NO_TIMER"}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "tok")
	if _, err := c.StopTimer(context.Background()); err == nil {
		t.Fatal("expected error on 400")
	}
}
