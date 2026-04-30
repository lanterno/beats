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

// postJSON sends a JSON POST request to the given path with Bearer auth.
func (c *Client) postJSON(ctx context.Context, path string, body any) error {
	data, err := json.Marshal(body)
	if err != nil {
		return fmt.Errorf("marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		c.baseURL+path, bytes.NewReader(data))
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if c.deviceToken != "" {
		req.Header.Set("Authorization", "Bearer "+c.deviceToken)
	}

	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("request to %s failed: %w", path, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("request to %s failed (HTTP %d): %s", path, resp.StatusCode, string(respBody))
	}

	return nil
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

// ExchangePairCode exchanges a pairing code for a device token.
// This endpoint is public and does not require authentication.
func (c *Client) ExchangePairCode(ctx context.Context, code, deviceName string) (*PairExchangeResponse, error) {
	body := map[string]string{"code": code}
	if deviceName != "" {
		body["device_name"] = deviceName
	}

	data, err := json.Marshal(body)
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		c.baseURL+"/api/device/pair/exchange", bytes.NewReader(data))
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("exchange request failed: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("exchange failed (HTTP %d): %s", resp.StatusCode, string(respBody))
	}

	var result PairExchangeResponse
	if err := json.Unmarshal(respBody, &result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	return &result, nil
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
	req, err := http.NewRequestWithContext(ctx, http.MethodGet,
		c.baseURL+"/api/signals/flow-windows?"+q.Encode(), nil)
	if err != nil {
		return nil, err
	}
	if c.deviceToken != "" {
		req.Header.Set("Authorization", "Bearer "+c.deviceToken)
	}

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("flow-windows GET failed (HTTP %d)", resp.StatusCode)
	}

	var out []FlowWindowRecord
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return out, nil
}

// TimerContextResponse is the response from GET /api/signals/timer-context.
type TimerContextResponse struct {
	TimerRunning    bool   `json:"timer_running"`
	ProjectID       string `json:"project_id,omitempty"`
	ProjectCategory string `json:"project_category,omitempty"`
}

// GetTimerContext fetches the current timer state for flow score context.
func (c *Client) GetTimerContext(ctx context.Context) (*TimerContextResponse, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet,
		c.baseURL+"/api/signals/timer-context", nil)
	if err != nil {
		return nil, err
	}
	if c.deviceToken != "" {
		req.Header.Set("Authorization", "Bearer "+c.deviceToken)
	}

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("timer-context failed (HTTP %d)", resp.StatusCode)
	}

	var result TimerContextResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}
	return &result, nil
}

// AutoTimerSuggestion is the response from POST /api/signals/suggest-timer.
type AutoTimerSuggestion struct {
	ShouldSuggest bool   `json:"should_suggest"`
	ProjectID     string `json:"project_id,omitempty"`
	ProjectName   string `json:"project_name,omitempty"`
}

// SuggestTimer asks the API if a timer should be auto-started.
func (c *Client) SuggestTimer(ctx context.Context, w FlowWindowRequest) (*AutoTimerSuggestion, error) {
	data, err := json.Marshal(w)
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		c.baseURL+"/api/signals/suggest-timer", bytes.NewReader(data))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	if c.deviceToken != "" {
		req.Header.Set("Authorization", "Bearer "+c.deviceToken)
	}

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("suggest-timer failed (HTTP %d)", resp.StatusCode)
	}

	var result AutoTimerSuggestion
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}
	return &result, nil
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
