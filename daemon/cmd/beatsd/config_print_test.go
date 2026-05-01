package main

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/ahmedElghable/beats/daemon/internal/config"
)

func TestFormatConfig_RendersAllSections(t *testing.T) {
	cfg := &config.Config{}
	cfg.API.BaseURL = "https://api.example.com"
	cfg.UI.BaseURL = "https://app.example.com"
	cfg.Collector.PollIntervalSec = 5
	cfg.Collector.FlushIntervalSec = 60

	out := formatConfig(cfg)

	for _, want := range []string{
		"[api]",
		"https://api.example.com",
		"[ui]",
		"https://app.example.com",
		"[collector]",
		"poll_interval_sec",
		"flush_interval_sec",
		"5",
		"60",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("expected output to contain %q, got:\n%s", want, out)
		}
	}
}

func TestFormatConfig_MentionsTheConfigFilePath(t *testing.T) {
	// Surface the path so the user can `cat` / edit it if something's
	// off. The path comes from config.ConfigPath() which is HOME-
	// based, so we just check that the line is present rather than
	// asserting a specific value (varies by test runner).
	cfg := &config.Config{}
	out := formatConfig(cfg)
	if !strings.Contains(out, "config:") {
		t.Errorf("expected 'config:' label, got:\n%s", out)
	}
}

func TestFormatConfigJSON_RoundTripsAndExposesFields(t *testing.T) {
	// Output must parse back into a sensible shape — `beatsd config
	// --json | jq -r .ui.base_url` should work without `tail` or
	// `grep` chicanery.
	cfg := &config.Config{}
	cfg.API.BaseURL = "https://api.example.com"
	cfg.UI.BaseURL = "https://app.example.com"
	cfg.Collector.PollIntervalSec = 7
	cfg.Collector.FlushIntervalSec = 75

	out, err := formatConfigJSON(cfg)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.HasSuffix(out, "\n") {
		t.Errorf("expected trailing newline so shell prompts land cleanly, got %q", out)
	}

	var got map[string]any
	if err := json.Unmarshal([]byte(out), &got); err != nil {
		t.Fatalf("output should round-trip through json.Unmarshal: %v\noutput: %s", err, out)
	}
	api, _ := got["api"].(map[string]any)
	if api["base_url"] != "https://api.example.com" {
		t.Errorf("api.base_url wrong, got %v", api["base_url"])
	}
	ui, _ := got["ui"].(map[string]any)
	if ui["base_url"] != "https://app.example.com" {
		t.Errorf("ui.base_url wrong, got %v", ui["base_url"])
	}
	collector, _ := got["collector"].(map[string]any)
	// JSON unmarshals numbers as float64 — compare via float comparison.
	if collector["poll_interval_sec"].(float64) != 7 {
		t.Errorf("poll_interval_sec wrong, got %v", collector["poll_interval_sec"])
	}
}

func TestFormatConfigJSON_DoesNotLeakDeviceToken(t *testing.T) {
	// Same regression class as the human-formatted variant — the JSON
	// output is even more likely to land in scripts that log to disk.
	cfg := &config.Config{}
	cfg.API.DeviceToken = "secret-do-not-leak"
	out, err := formatConfigJSON(cfg)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if strings.Contains(out, "secret-do-not-leak") {
		t.Errorf("formatConfigJSON leaked the device token, got:\n%s", out)
	}
	if strings.Contains(strings.ToLower(out), "device_token") ||
		strings.Contains(strings.ToLower(out), "devicetoken") {
		t.Errorf("formatConfigJSON should not mention the token field name, got:\n%s", out)
	}
}

func TestFormatConfig_DoesNotLeakDeviceToken(t *testing.T) {
	// Device token is in the keychain, not the config file — but the
	// runtime Config struct DOES have a DeviceToken field that gets
	// populated at startup. The config printer must NOT include it
	// since the output is the kind of thing users paste into bug
	// reports / screenshots / Claude conversations.
	cfg := &config.Config{}
	cfg.API.DeviceToken = "secret-do-not-leak"
	out := formatConfig(cfg)

	if strings.Contains(out, "secret-do-not-leak") {
		t.Errorf("formatConfig leaked the device token, got:\n%s", out)
	}
	if strings.Contains(strings.ToLower(out), "device_token") ||
		strings.Contains(strings.ToLower(out), "devicetoken") {
		t.Errorf("formatConfig should not even mention the token field name, got:\n%s", out)
	}
}
