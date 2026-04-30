package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestDefaultConfig(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.API.BaseURL != "http://localhost:7999" {
		t.Errorf("expected default base_url http://localhost:7999, got %s", cfg.API.BaseURL)
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
