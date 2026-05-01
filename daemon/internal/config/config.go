// Package config handles daemon configuration from ~/.config/beats/daemon.toml.
package config

import (
	"os"
	"path/filepath"

	"github.com/BurntSushi/toml"
)

// Config is the top-level daemon configuration.
type Config struct {
	API       APIConfig       `toml:"api"`
	UI        UIConfig        `toml:"ui"`
	Collector CollectorConfig `toml:"collector"`
}

// APIConfig holds API connection settings.
type APIConfig struct {
	BaseURL     string `toml:"base_url"`
	DeviceToken string `toml:"-"` // Set at runtime from keychain, not config file
}

// UIConfig holds the web UI URL — used by `beatsd open` to deep-link
// the analytics page in the system browser. Distinct from API.BaseURL
// because deployments commonly host the API and the SPA on different
// hosts (api.example.com vs app.example.com).
type UIConfig struct {
	BaseURL string `toml:"base_url"`
}

// CollectorConfig controls signal collection timing.
type CollectorConfig struct {
	PollIntervalSec  int `toml:"poll_interval_sec"`  // How often to sample (default 5s)
	FlushIntervalSec int `toml:"flush_interval_sec"` // How often to compute + send a FlowWindow (default 60s)
}

// DefaultConfig returns a Config with sensible defaults for local development.
func DefaultConfig() *Config {
	return &Config{
		API: APIConfig{
			BaseURL: "http://localhost:7999",
		},
		UI: UIConfig{
			BaseURL: "http://localhost:8080",
		},
		Collector: CollectorConfig{
			PollIntervalSec:  5,
			FlushIntervalSec: 60,
		},
	}
}

// ConfigPath returns the default path to the daemon config file.
func ConfigPath() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return ""
	}
	return filepath.Join(home, ".config", "beats", "daemon.toml")
}

// Load reads the daemon config from disk. If the file does not exist,
// it returns DefaultConfig without error (first-run before pairing).
func Load() (*Config, error) {
	return LoadFrom(ConfigPath())
}

// LoadFrom reads config from a specific path.
func LoadFrom(path string) (*Config, error) {
	cfg := DefaultConfig()

	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return cfg, nil
		}
		return nil, err
	}

	if err := toml.Unmarshal(data, cfg); err != nil {
		return nil, err
	}

	return cfg, nil
}
