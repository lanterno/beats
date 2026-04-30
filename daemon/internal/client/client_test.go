package client

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestExchangePairCodeSuccess(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		if r.URL.Path != "/api/device/pair/exchange" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}

		var body map[string]string
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		if body["code"] != "ABC123" {
			t.Errorf("expected code ABC123, got %s", body["code"])
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(PairExchangeResponse{
			DeviceToken: "tok_device_123",
			DeviceID:    "dev-uuid",
		})
	}))
	defer srv.Close()

	c := New(srv.URL, "")
	resp, err := c.ExchangePairCode(context.Background(), "ABC123", "my-mac")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.DeviceToken != "tok_device_123" {
		t.Errorf("expected device token tok_device_123, got %s", resp.DeviceToken)
	}
	if resp.DeviceID != "dev-uuid" {
		t.Errorf("expected device ID dev-uuid, got %s", resp.DeviceID)
	}
}

func TestExchangePairCodeError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		w.Write([]byte(`{"detail":"Invalid or expired pairing code"}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "")
	_, err := c.ExchangePairCode(context.Background(), "BADCOD", "")
	if err == nil {
		t.Fatal("expected error for 404 response")
	}
}

func TestPostHeartbeatSetsAuthHeader(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		auth := r.Header.Get("Authorization")
		if auth != "Bearer test-device-token" {
			t.Errorf("expected Bearer test-device-token, got %s", auth)
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "test-device-token")
	if err := c.PostHeartbeat(context.Background()); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestPostFlowWindow(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		if r.URL.Path != "/api/signals/flow-windows" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		auth := r.Header.Get("Authorization")
		if auth != "Bearer dev-token" {
			t.Errorf("expected Bearer dev-token, got %s", auth)
		}

		var body FlowWindowRequest
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		if body.FlowScore < 0.5 || body.FlowScore > 0.7 {
			t.Errorf("unexpected flow score: %f", body.FlowScore)
		}
		if body.DominantBundleID != "com.apple.dt.Xcode" {
			t.Errorf("unexpected bundle ID: %s", body.DominantBundleID)
		}

		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"id": "abc123"}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "dev-token")
	now := time.Now().UTC()
	err := c.PostFlowWindow(context.Background(), FlowWindowRequest{
		WindowStart:      now.Add(-time.Minute),
		WindowEnd:        now,
		FlowScore:        0.6,
		CadenceScore:     0.5,
		CoherenceScore:   1.0,
		CategoryFitScore: 0.0,
		IdleFraction:     0.0,
		DominantBundleID: "com.apple.dt.Xcode",
		DominantCategory: "coding",
		ContextSwitches:  0,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestPostFlowWindow_IncludesEditorContext(t *testing.T) {
	// Editor context fields round-trip on the wire when set.
	var captured FlowWindowRequest
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewDecoder(r.Body).Decode(&captured)
		w.Write([]byte(`{"id":"abc"}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "dev-token")
	now := time.Now().UTC()
	err := c.PostFlowWindow(context.Background(), FlowWindowRequest{
		WindowStart:    now.Add(-time.Minute),
		WindowEnd:      now,
		EditorRepo:     "/Users/me/code/example",
		EditorBranch:   "main",
		EditorLanguage: "go",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if captured.EditorRepo != "/Users/me/code/example" {
		t.Errorf("editor_repo did not round-trip, got %q", captured.EditorRepo)
	}
	if captured.EditorBranch != "main" {
		t.Errorf("editor_branch did not round-trip, got %q", captured.EditorBranch)
	}
	if captured.EditorLanguage != "go" {
		t.Errorf("editor_language did not round-trip, got %q", captured.EditorLanguage)
	}
}

func TestPostFlowWindow_OmitsEmptyEditorContext(t *testing.T) {
	// When editor fields are zero-valued, they should not appear in the
	// JSON payload at all (omitempty). Saves a few bytes per request and
	// makes "no editor active" distinguishable from "editor sent ''".
	var raw []byte
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ = io.ReadAll(r.Body)
		w.Write([]byte(`{"id":"abc"}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "dev-token")
	now := time.Now().UTC()
	if err := c.PostFlowWindow(context.Background(), FlowWindowRequest{
		WindowStart: now.Add(-time.Minute),
		WindowEnd:   now,
	}); err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"editor_repo", "editor_branch", "editor_language"} {
		if strings.Contains(string(raw), key) {
			t.Errorf("expected %s to be omitted from payload, got %s", key, raw)
		}
	}
}

func TestPostFlowWindowError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
		w.Write([]byte(`{"error":"forbidden"}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "bad-token")
	err := c.PostFlowWindow(context.Background(), FlowWindowRequest{})
	if err == nil {
		t.Fatal("expected error for 403")
	}
}
