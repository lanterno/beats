// Package client provides an HTTP client for the Beats API with device token auth.
package client

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"
)

// errorEnvelope mirrors the API's unified error shape (api/src/beats/api/errors.py):
//
//	{"detail": "human-readable message", "code": "MACHINE_READABLE_CODE"}
//
// We only need detail + code here — the optional `fields` array is
// validation-error specific and useful enough on its own that callers
// currently don't need to read it; if that changes we can grow this
// struct.
type errorEnvelope struct {
	Detail string `json:"detail"`
	Code   string `json:"code"`
}

// describeErrorBody parses the response body as the API's error envelope
// and renders it as a single suffix the caller can attach to a
// "<thing> failed (HTTP N)" sentence.
//
// Returns the raw body text when JSON parsing fails (older API versions
// or upstream proxies returning HTML 502s), or an empty string for an
// empty body so callers don't print a trailing colon followed by
// nothing. The empty-body case matters: status-code-only failures
// (e.g. a network race that returns 503 before the API can encode)
// previously read fine because the format string didn't include `:%s`.
func describeErrorBody(body []byte) string {
	if len(body) == 0 {
		return ""
	}
	var env errorEnvelope
	if err := json.Unmarshal(body, &env); err == nil && (env.Detail != "" || env.Code != "") {
		switch {
		case env.Detail != "" && env.Code != "":
			return fmt.Sprintf("%s [%s]", env.Detail, env.Code)
		case env.Detail != "":
			return env.Detail
		default:
			return env.Code
		}
	}
	// Trim ASCII whitespace so a stray newline doesn't produce a
	// "failed (HTTP 500): \n" rendering.
	return string(bytes.TrimSpace(body))
}

// do sends one API call and returns the response body, having already
// checked the status and rendered any error envelope. `op` names the
// operation for the error message, e.g. "flow-windows GET".
//
// Every request the daemon makes went through this shape by hand before:
// build, set Content-Type when there is a body, attach the device token,
// send, check the status, read the envelope, decode. Eight copies of it
// drifted in small ways — some checked `!= 200`, others `>= 300`.
func (c *Client) do(ctx context.Context, method, path string, body any, op string) ([]byte, error) {
	var reader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("marshal %s request: %w", op, err)
		}
		reader = bytes.NewReader(data)
	}

	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, reader)
	if err != nil {
		return nil, fmt.Errorf("create %s request: %w", op, err)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	// Empty on the pairing exchange, which is public by design.
	if c.deviceToken != "" {
		req.Header.Set("Authorization", "Bearer "+c.deviceToken)
	}

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("%s request failed: %w", op, err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read %s response: %w", op, err)
	}

	if resp.StatusCode >= 300 {
		if detail := describeErrorBody(respBody); detail != "" {
			return nil, fmt.Errorf("%s failed (HTTP %d): %s", op, resp.StatusCode, detail)
		}
		return nil, fmt.Errorf("%s failed (HTTP %d)", op, resp.StatusCode)
	}
	return respBody, nil
}

// fetch is do plus a JSON decode. A free function rather than a method
// because Go does not allow type parameters on methods.
func fetch[T any](ctx context.Context, c *Client, method, path string, body any, op string) (T, error) {
	var out T
	respBody, err := c.do(ctx, method, path, body, op)
	if err != nil {
		return out, err
	}
	if err := json.Unmarshal(respBody, &out); err != nil {
		return out, fmt.Errorf("decode %s response: %w", op, err)
	}
	return out, nil
}

// postJSON sends a JSON POST request to the given path with Bearer auth.
func (c *Client) postJSON(ctx context.Context, path string, body any) error {
	_, err := c.do(ctx, http.MethodPost, path, body, "request to "+path)
	return err
}

// Client is an HTTP client for the Beats API.
type Client struct {
	baseURL     string
	deviceToken string
	http        *http.Client
}

// PairExchangeResponse is the response from POST /api/device/pair/exchange.
type PairExchangeResponse struct {
	DeviceToken string `json:"device_token"`
	DeviceID    string `json:"device_id"`
}

// New creates a new API client. If deviceToken is empty, only pairing
// endpoints can be called.
func New(baseURL, deviceToken string) *Client {
	return &Client{
		baseURL:     baseURL,
		deviceToken: deviceToken,
		http: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

// Project is the minimal projection of GET /api/projects needed to
// resolve a name hint to a project for timer control.
type Project struct {
	ID       string `json:"id"`
	Name     string `json:"name"`
	Archived bool   `json:"archived"`
}

// GetProjects lists the user's projects (active and archived). Used by
// `beatsd start <hint>` to resolve the hint to a project id.
func (c *Client) GetProjects(ctx context.Context) ([]Project, error) {
	return fetch[[]Project](ctx, c, http.MethodGet, "/api/projects/", nil, "list projects")
}

// StartTimer starts a timer for the given project. The start time is
// omitted so the server stamps it "now" (RecordTimeRequest defaults to
// now when `time` is absent).
func (c *Client) StartTimer(ctx context.Context, projectID string) error {
	return c.postJSON(ctx, "/api/projects/"+url.PathEscape(projectID)+"/start", map[string]any{})
}

// StoppedBeat is the subset of the stop response we render (the API
// returns the full beat; we only need the project + span).
type StoppedBeat struct {
	ProjectID string    `json:"project_id"`
	Start     time.Time `json:"start"`
	End       time.Time `json:"end"`
}

// StopTimer stops the currently running timer and returns the completed
// beat so the caller can report the logged duration.
func (c *Client) StopTimer(ctx context.Context) (*StoppedBeat, error) {
	beat, err := fetch[*StoppedBeat](
		ctx, c, http.MethodPost, "/api/projects/stop", map[string]any{}, "stop timer",
	)
	if err != nil {
		return nil, err
	}
	return beat, nil
}

// ExchangePairCode exchanges a pairing code for a device token.
// This endpoint is public and does not require authentication.
func (c *Client) ExchangePairCode(ctx context.Context, code, deviceName string) (*PairExchangeResponse, error) {
	body := map[string]string{"code": code}
	if deviceName != "" {
		body["device_name"] = deviceName
	}
	return fetch[*PairExchangeResponse](
		ctx, c, http.MethodPost, "/api/device/pair/exchange", body, "exchange",
	)
}

// FlowWindowRequest is the body for POST /api/signals/flow-windows.
type FlowWindowRequest struct {
	WindowStart      time.Time `json:"window_start"`
	WindowEnd        time.Time `json:"window_end"`
	FlowScore        float64   `json:"flow_score"`
	CadenceScore     float64   `json:"cadence_score"`
	CoherenceScore   float64   `json:"coherence_score"`
	CategoryFitScore float64   `json:"category_fit_score"`
	IdleFraction     float64   `json:"idle_fraction"`
	DominantBundleID string    `json:"dominant_bundle_id"`
	DominantCategory string    `json:"dominant_category"`
	ContextSwitches  int       `json:"context_switches"`
	ActiveProjectID  string    `json:"active_project_id,omitempty"`
	// Editor heartbeat snapshot, populated from editor.Listener.Latest()
	// when the window flushes. omitempty so windows without an editor
	// active don't waste payload bytes on null fields.
	EditorRepo     string `json:"editor_repo,omitempty"`
	EditorBranch   string `json:"editor_branch,omitempty"`
	EditorLanguage string `json:"editor_language,omitempty"`
}

// PostFlowWindow sends a computed flow window to the API. Requires a device token.
func (c *Client) PostFlowWindow(ctx context.Context, w FlowWindowRequest) error {
	return c.postJSON(ctx, "/api/signals/flow-windows", w)
}

// FlowWindowRecord is the shape returned by GET /api/signals/flow-windows.
// Mirrors the API's FlowWindowResponse — superset of FlowWindowRequest
// because the API stamps an id on persistence.
type FlowWindowRecord struct {
	ID               string    `json:"id"`
	WindowStart      time.Time `json:"window_start"`
	WindowEnd        time.Time `json:"window_end"`
	FlowScore        float64   `json:"flow_score"`
	CadenceScore     float64   `json:"cadence_score"`
	CoherenceScore   float64   `json:"coherence_score"`
	CategoryFitScore float64   `json:"category_fit_score"`
	IdleFraction     float64   `json:"idle_fraction"`
	DominantBundleID string    `json:"dominant_bundle_id"`
	DominantCategory string    `json:"dominant_category"`
	ContextSwitches  int       `json:"context_switches"`
	ActiveProjectID  string    `json:"active_project_id,omitempty"`
	EditorRepo       string    `json:"editor_repo,omitempty"`
	EditorBranch     string    `json:"editor_branch,omitempty"`
	EditorLanguage   string    `json:"editor_language,omitempty"`
}

// FlowWindowsFilter narrows the result of GetFlowWindows. Empty fields
// are omitted from the URL — same shape the API expects, AND-composed
// server-side. Used by `beatsd recent --repo …` and friends.
type FlowWindowsFilter struct {
	EditorRepo     string
	EditorLanguage string
	BundleID       string
}

// GetFlowWindows lists flow windows for the device's user in [start, end].
// Used by `beatsd recent` to show the last N minutes of activity without
// the user having to open the web UI.
func (c *Client) GetFlowWindows(ctx context.Context, start, end time.Time) ([]FlowWindowRecord, error) {
	return c.GetFlowWindowsFiltered(ctx, start, end, FlowWindowsFilter{})
}

// GetFlowWindowsFiltered is GetFlowWindows with optional server-side
// filters. Kept as a separate method so existing call sites (and the
// older daemon flows) don't need to thread a filter struct through.
func (c *Client) GetFlowWindowsFiltered(
	ctx context.Context,
	start, end time.Time,
	filter FlowWindowsFilter,
) ([]FlowWindowRecord, error) {
	q := url.Values{}
	q.Set("start", start.UTC().Format(time.RFC3339))
	q.Set("end", end.UTC().Format(time.RFC3339))
	if filter.EditorRepo != "" {
		q.Set("editor_repo", filter.EditorRepo)
	}
	if filter.EditorLanguage != "" {
		q.Set("editor_language", filter.EditorLanguage)
	}
	if filter.BundleID != "" {
		q.Set("bundle_id", filter.BundleID)
	}
	return fetch[[]FlowWindowRecord](
		ctx, c, http.MethodGet,
		"/api/signals/flow-windows?"+q.Encode(), nil, "flow-windows GET",
	)
}

// FlowWindowSummary mirrors the API's FlowWindowSummaryResponse — a
// single-round-trip aggregate for the same slice GetFlowWindowsFiltered
// would page through. PeakAt is a pointer so the empty-slice case
// (count=0) is distinguishable from "peak at the zero time".
type FlowWindowSummary struct {
	Count       int          `json:"count"`
	Avg         float64      `json:"avg"`
	Peak        float64      `json:"peak"`
	PeakAt      *time.Time   `json:"peak_at"`
	TopRepo     *FlowTopItem `json:"top_repo"`
	TopLanguage *FlowTopItem `json:"top_language"`
	TopBundle   *FlowTopItem `json:"top_bundle"`
}

// FlowTopItem is one bucket inside a FlowWindowSummary axis. Same shape
// as the API's TopBucket — the highest-count entry on its grouping axis.
type FlowTopItem struct {
	Key   string  `json:"key"`
	Avg   float64 `json:"avg"`
	Count int     `json:"count"`
}

// GetFlowWindowsSummary fetches single round-trip aggregate stats for
// the slice [start, end] under the given filter. Used by `beatsd stats`
// to render a one-line headline without paginating every row.
func (c *Client) GetFlowWindowsSummary(
	ctx context.Context,
	start, end time.Time,
	filter FlowWindowsFilter,
) (*FlowWindowSummary, error) {
	q := url.Values{}
	q.Set("start", start.UTC().Format(time.RFC3339))
	q.Set("end", end.UTC().Format(time.RFC3339))
	if filter.EditorRepo != "" {
		q.Set("editor_repo", filter.EditorRepo)
	}
	if filter.EditorLanguage != "" {
		q.Set("editor_language", filter.EditorLanguage)
	}
	if filter.BundleID != "" {
		q.Set("bundle_id", filter.BundleID)
	}
	return fetch[*FlowWindowSummary](
		ctx, c, http.MethodGet,
		"/api/signals/flow-windows/summary?"+q.Encode(), nil, "flow-windows summary GET",
	)
}

// TimerContextResponse is the response from GET /api/signals/timer-context.
type TimerContextResponse struct {
	TimerRunning    bool   `json:"timer_running"`
	ProjectID       string `json:"project_id,omitempty"`
	ProjectCategory string `json:"project_category,omitempty"`
}

// GetTimerContext fetches the current timer state for flow score context.
func (c *Client) GetTimerContext(ctx context.Context) (*TimerContextResponse, error) {
	return fetch[*TimerContextResponse](
		ctx, c, http.MethodGet, "/api/signals/timer-context", nil, "timer-context",
	)
}

// AutoTimerSuggestion is the response from POST /api/signals/suggest-timer.
type AutoTimerSuggestion struct {
	ShouldSuggest bool   `json:"should_suggest"`
	ProjectID     string `json:"project_id,omitempty"`
	ProjectName   string `json:"project_name,omitempty"`
}

// SuggestTimer asks the API if a timer should be auto-started.
func (c *Client) SuggestTimer(ctx context.Context, w FlowWindowRequest) (*AutoTimerSuggestion, error) {
	return fetch[*AutoTimerSuggestion](
		ctx, c, http.MethodPost, "/api/signals/suggest-timer", w, "suggest-timer",
	)
}

// DriftEventRequest is the body for POST /api/signals/drift.
type DriftEventRequest struct {
	StartedAt       time.Time `json:"started_at"`
	DurationSeconds float64   `json:"duration_seconds"`
	BundleID        string    `json:"bundle_id"`
}

// PostDriftEvent reports a distraction drift event to the API.
func (c *Client) PostDriftEvent(ctx context.Context, d DriftEventRequest) error {
	return c.postJSON(ctx, "/api/signals/drift", d)
}

// PostHeartbeat sends a heartbeat to the API. Requires a device token.
func (c *Client) PostHeartbeat(ctx context.Context) error {
	return c.postJSON(ctx, "/api/device/heartbeat", struct{}{})
}
