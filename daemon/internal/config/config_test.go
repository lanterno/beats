package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestDefaultConfig(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.API.BaseURL != "http://localhost:7999" {
		t.Errorf("expected default api.base_url http://localhost:7999, got %s", cfg.API.BaseURL)
	}
	if cfg.UI.BaseURL != "http://localhost:8080" {
		t.Errorf("expected default ui.base_url http://localhost:8080, got %s", cfg.UI.BaseURL)
	}
}

func TestLoadFromMissingFile(t *testing.T) {
	cfg, err := LoadFrom("/nonexistent/path/daemon.toml")
	if err != nil {
		t.Fatalf("expected nil error for missing file, got %v", err)
	}
	if cfg.API.BaseURL != "http://localhost:7999" {
		t.Errorf("expected default base_url, got %s", cfg.API.BaseURL)
	}
}

func TestLoadFromValidFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "daemon.toml")

	content := `[api]
base_url = "https://api.lifepete.com"
`
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	cfg, err := LoadFrom(path)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.API.BaseURL != "https://api.lifepete.com" {
		t.Errorf("expected custom base_url, got %s", cfg.API.BaseURL)
	}
}

func TestLoadFromInvalidToml(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "daemon.toml")

	if err := os.WriteFile(path, []byte("invalid [[[toml"), 0644); err != nil {
		t.Fatal(err)
	}

	_, err := LoadFrom(path)
	if err == nil {
		t.Fatal("expected error for invalid TOML")
	}
}

func TestDefaultCollectorIntervals(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.Collector.PollIntervalSec <= 0 {
		t.Errorf("PollIntervalSec must be > 0, got %d", cfg.Collector.PollIntervalSec)
	}
	if cfg.Collector.FlushIntervalSec <= 0 {
		t.Errorf("FlushIntervalSec must be > 0, got %d", cfg.Collector.FlushIntervalSec)
	}
	// FlushInterval should be a multiple of PollInterval — windows are built
	// from samples, and a flush mid-sample produces a partial window.
	if cfg.Collector.FlushIntervalSec%cfg.Collector.PollIntervalSec != 0 {
		t.Errorf("FlushIntervalSec (%d) should be a multiple of PollIntervalSec (%d)",
			cfg.Collector.FlushIntervalSec, cfg.Collector.PollIntervalSec)
	}
}

func TestLoadFromPartialFileKeepsDefaults(t *testing.T) {
	// User overrides only base_url. Collector defaults must NOT zero out;
	// otherwise pollInterval=0 would melt the loop on first run after the
	// user set just one field in their daemon.toml.
	dir := t.TempDir()
	path := filepath.Join(dir, "daemon.toml")
	if err := os.WriteFile(path,
		[]byte("[api]\nbase_url = \"https://api.example.com\"\n"), 0644); err != nil {
		t.Fatal(err)
	}
	cfg, err := LoadFrom(path)
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	def := DefaultConfig()
	if cfg.API.BaseURL != "https://api.example.com" {
		t.Errorf("override should apply: %s", cfg.API.BaseURL)
	}
	if cfg.Collector.PollIntervalSec != def.Collector.PollIntervalSec {
		t.Errorf("PollIntervalSec lost on partial config: %d", cfg.Collector.PollIntervalSec)
	}
	if cfg.Collector.FlushIntervalSec != def.Collector.FlushIntervalSec {
		t.Errorf("FlushIntervalSec lost on partial config: %d", cfg.Collector.FlushIntervalSec)
	}
}

func TestLoadFromOverridesCollectorIntervals(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "daemon.toml")
	contents := `
[collector]
poll_interval_sec = 10
flush_interval_sec = 120
`
	if err := os.WriteFile(path, []byte(contents), 0644); err != nil {
		t.Fatal(err)
	}
	cfg, err := LoadFrom(path)
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if cfg.Collector.PollIntervalSec != 10 {
		t.Errorf("PollIntervalSec not overridden: %d", cfg.Collector.PollIntervalSec)
	}
	if cfg.Collector.FlushIntervalSec != 120 {
		t.Errorf("FlushIntervalSec not overridden: %d", cfg.Collector.FlushIntervalSec)
	}
}

func TestLoadFromIgnoresDeviceTokenFromDisk(t *testing.T) {
	// Security-critical: the device token lives in the OS keychain, never
	// in the config file. APIConfig has `toml:"-"` on DeviceToken so even
	// a file that accidentally declares it should NOT load it. If this
	// test regresses, someone has changed the toml tag.
	dir := t.TempDir()
	path := filepath.Join(dir, "daemon.toml")
	contents := `
[api]
base_url = "http://localhost:7999"
device_token = "should-NEVER-load-from-disk"
`
	if err := os.WriteFile(path, []byte(contents), 0644); err != nil {
		t.Fatal(err)
	}
	cfg, err := LoadFrom(path)
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if cfg.API.DeviceToken != "" {
		t.Errorf("device_token must never load from disk; got %q", cfg.API.DeviceToken)
	}
}

func TestDefaultScoring(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.Scoring.CadenceWeight != 0.4 {
		t.Errorf("default cadence_weight should be 0.4, got %f", cfg.Scoring.CadenceWeight)
	}
	if cfg.Scoring.CoherenceWeight != 0.4 {
		t.Errorf("default coherence_weight should be 0.4, got %f", cfg.Scoring.CoherenceWeight)
	}
	if cfg.Scoring.CategoryWeight != 0.2 {
		t.Errorf("default category_weight should be 0.2, got %f", cfg.Scoring.CategoryWeight)
	}
	if cfg.Scoring.IdleThresholdSec != 30 {
		t.Errorf("default idle_threshold_sec should be 30, got %f", cfg.Scoring.IdleThresholdSec)
	}
	// Weights sum to ~1.0 — the formula doesn't enforce this but the
	// ship default does so the score has the natural [0,1] range.
	sum := cfg.Scoring.CadenceWeight + cfg.Scoring.CoherenceWeight + cfg.Scoring.CategoryWeight
	if sum < 0.99 || sum > 1.01 {
		t.Errorf("default scoring weights should sum to ~1.0, got %f", sum)
	}
}

func TestLoadFromOverridesScoring(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "daemon.toml")
	contents := `
[scoring]
cadence_weight = 0.5
coherence_weight = 0.3
category_weight = 0.2
idle_threshold_sec = 60
`
	if err := os.WriteFile(path, []byte(contents), 0644); err != nil {
		t.Fatal(err)
	}
	cfg, err := LoadFrom(path)
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if cfg.Scoring.CadenceWeight != 0.5 {
		t.Errorf("cadence_weight not overridden: %f", cfg.Scoring.CadenceWeight)
	}
	if cfg.Scoring.IdleThresholdSec != 60 {
		t.Errorf("idle_threshold_sec not overridden: %f", cfg.Scoring.IdleThresholdSec)
	}
}

func TestLoadFromMissingScoringKeepsDefaults(t *testing.T) {
	// A daemon.toml without a [scoring] section must keep the shipped
	// defaults — otherwise users on an older config (no [scoring]
	// section) would silently zero out their flow score after upgrade.
	dir := t.TempDir()
	path := filepath.Join(dir, "daemon.toml")
	if err := os.WriteFile(path, []byte("[collector]\npoll_interval_sec = 5\n"), 0644); err != nil {
		t.Fatal(err)
	}
	cfg, err := LoadFrom(path)
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	def := DefaultConfig()
	if cfg.Scoring != def.Scoring {
		t.Errorf("scoring section without [scoring] should match defaults, got %+v", cfg.Scoring)
	}
}

func TestConfigPath_LooksLikeXdgConfig(t *testing.T) {
	p := ConfigPath()
	if p == "" {
		t.Skip("no $HOME in this environment")
	}
	// Path should end in .config/beats/daemon.toml. Don't pin the home
	// segment — that varies per machine / per CI runner.
	if got := filepath.Base(p); got != "daemon.toml" {
		t.Errorf("expected basename daemon.toml, got %q", got)
	}
	if got := filepath.Base(filepath.Dir(p)); got != "beats" {
		t.Errorf("expected parent dir beats, got %q", got)
	}
	if got := filepath.Base(filepath.Dir(filepath.Dir(p))); got != ".config" {
		t.Errorf("expected grandparent .config, got %q", got)
	}
}
