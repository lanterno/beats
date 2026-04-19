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
