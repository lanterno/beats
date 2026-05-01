package client

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
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

func TestGetFlowWindowsFiltered_EncodesQueryParams(t *testing.T) {
	// Verifies the client sends each FlowWindowsFilter field as the
	// matching API query param. Empty fields are omitted entirely so a
	// no-filter call doesn't gain noisy `editor_repo=` empties.
	var got url.Values
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got = r.URL.Query()
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`[]`))
	}))
	defer srv.Close()

	c := New(srv.URL, "dev-token")
	now := time.Now().UTC()
	_, err := c.GetFlowWindowsFiltered(context.Background(), now.Add(-time.Hour), now, FlowWindowsFilter{
		EditorRepo:     "/Users/me/code/beats",
		EditorLanguage: "go",
		BundleID:       "com.microsoft.VSCode",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if got.Get("editor_repo") != "/Users/me/code/beats" {
		t.Errorf("editor_repo not encoded, got %q", got.Get("editor_repo"))
	}
	if got.Get("editor_language") != "go" {
		t.Errorf("editor_language not encoded, got %q", got.Get("editor_language"))
	}
	if got.Get("bundle_id") != "com.microsoft.VSCode" {
		t.Errorf("bundle_id not encoded, got %q", got.Get("bundle_id"))
	}
}

func TestGetFlowWindows_OmitsEmptyFilterParams(t *testing.T) {
	// Back-compat: the unfiltered GetFlowWindows must not introduce empty
	// `editor_repo=` keys — the API is happy ignoring them but they make
	// the URL noisy in logs and could collide with future params.
	var got url.Values
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got = r.URL.Query()
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`[]`))
	}))
	defer srv.Close()

	c := New(srv.URL, "dev-token")
	now := time.Now().UTC()
	if _, err := c.GetFlowWindows(context.Background(), now.Add(-time.Hour), now); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for _, key := range []string{"editor_repo", "editor_language", "bundle_id"} {
		if got.Has(key) {
			t.Errorf("expected %s to be absent from URL when filter empty, but it was present", key)
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

// describeErrorBody is the small helper that turns the API's unified
// error envelope ({detail, code}) into the suffix the daemon attaches
// to "<thing> failed (HTTP N)" sentences. Locked-in here so the
// readable form a `beatsd recent` user sees doesn't quietly regress.
func TestDescribeErrorBody_FullEnvelope(t *testing.T) {
	got := describeErrorBody([]byte(`{"detail":"Project archived","code":"PROJECT_ARCHIVED"}`))
	want := "Project archived [PROJECT_ARCHIVED]"
	if got != want {
		t.Errorf("expected %q, got %q", want, got)
	}
}

func TestDescribeErrorBody_DetailOnly(t *testing.T) {
	// Older API versions (pre-error-envelope) return just `{detail}`.
	// Daemon should still surface the human message rather than only
	// "(HTTP 404)" — that's the whole point of this helper.
	got := describeErrorBody([]byte(`{"detail":"Invalid or expired pairing code"}`))
	want := "Invalid or expired pairing code"
	if got != want {
		t.Errorf("expected %q, got %q", want, got)
	}
}

func TestDescribeErrorBody_CodeOnly(t *testing.T) {
	// Edge case — a router raised with a code but no message. The
	// envelope helper falls back to the code so the user at least sees
	// the machine-readable kind of failure.
	got := describeErrorBody([]byte(`{"code":"RATE_LIMITED"}`))
	want := "RATE_LIMITED"
	if got != want {
		t.Errorf("expected %q, got %q", want, got)
	}
}

func TestDescribeErrorBody_NonJsonFallsBackToTrimmedRaw(t *testing.T) {
	// Upstream proxies / load balancers can emit HTML 502s. The user
	// shouldn't see the JSON parse error — we just surface the raw
	// text trimmed of trailing newlines.
	got := describeErrorBody([]byte("Bad Gateway\n"))
	if got != "Bad Gateway" {
		t.Errorf("expected trimmed raw fallback, got %q", got)
	}
}

func TestDescribeErrorBody_EmptyReturnsEmpty(t *testing.T) {
	// Status-code-only failures (network race, explicit 503 with no
	// body) shouldn't render as "<thing> failed (HTTP 503): " with a
	// trailing colon followed by nothing — callers branch on empty.
	if got := describeErrorBody(nil); got != "" {
		t.Errorf("expected empty for nil body, got %q", got)
	}
	if got := describeErrorBody([]byte{}); got != "" {
		t.Errorf("expected empty for zero-length body, got %q", got)
	}
}

func TestDescribeErrorBody_JsonShapeNotEnvelopeFallsBackToRaw(t *testing.T) {
	// Some 4xx responses come from FastAPI's deeper internals or from
	// proxies — JSON-shaped but not our envelope. Surface the raw
	// JSON text rather than silently dropping it; "{}" tells the user
	// SOMETHING came back even when there's no detail.
	got := describeErrorBody([]byte(`{"unrelated":"shape"}`))
	if got != `{"unrelated":"shape"}` {
		t.Errorf("expected raw JSON when envelope keys absent, got %q", got)
	}
}

// End-to-end check that GetFlowWindowsFiltered surfaces the API's
// error detail in its returned error. Locks in that the rewired
// error path actually reaches the user — not just that the helper
// works in isolation.
func TestGetFlowWindowsFiltered_ErrorEnvelopeReachesUserFacingError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"detail":"Device token expired","code":"UNAUTHORIZED"}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "stale-token")
	now := time.Now()
	_, err := c.GetFlowWindowsFiltered(context.Background(), now.Add(-time.Hour), now, FlowWindowsFilter{})
	if err == nil {
		t.Fatal("expected an error")
	}
	if !strings.Contains(err.Error(), "Device token expired") {
		t.Errorf("expected detail to surface in error, got: %v", err)
	}
	if !strings.Contains(err.Error(), "UNAUTHORIZED") {
		t.Errorf("expected machine-readable code to surface in error, got: %v", err)
	}
	if !strings.Contains(err.Error(), "401") {
		t.Errorf("expected status code to remain in error, got: %v", err)
	}
}
