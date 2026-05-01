package main

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/ahmedElghable/beats/daemon/internal/config"
)

// runConfig prints the loaded daemon configuration in a human-readable
// shape. Useful when something feels off — `beatsd open` opens the
// wrong URL, the collector seems stuck on a stale interval — and the
// user wants to confirm what got loaded from disk vs the defaults.
//
// With `asJSON`, emits the same data as a JSON object — designed for
// shell scripts that want to consume specific fields:
//
//	beatsd config --json | jq -r .ui.base_url
//
// Device token is intentionally NOT printed in either mode: it lives
// in the keychain, not in this config struct, and even if it did the
// value is a credential the user shouldn't paste into screenshots /
// Claude pastes / pipelines that this command's output is likely to
// land in.
func runConfig(cfg *config.Config, asJSON bool) error {
	if asJSON {
		out, err := formatConfigJSON(cfg)
		if err != nil {
			return err
		}
		fmt.Print(out)
		return nil
	}
	fmt.Print(formatConfig(cfg))
	return nil
}

// formatConfigJSON renders the loaded config as a snake_case JSON
// object. Field names match the TOML keys so a script grepping for
// `base_url` works against either output. Device token field is
// excluded by virtue of not being included — we build a fresh
// shape rather than serializing the runtime Config struct directly,
// which would otherwise leak any future credential added to it.
func formatConfigJSON(cfg *config.Config) (string, error) {
	shape := map[string]any{
		"config_path": config.ConfigPath(),
		"api": map[string]any{
			"base_url": cfg.API.BaseURL,
		},
		"ui": map[string]any{
			"base_url": cfg.UI.BaseURL,
		},
		"collector": map[string]any{
			"poll_interval_sec":  cfg.Collector.PollIntervalSec,
			"flush_interval_sec": cfg.Collector.FlushIntervalSec,
		},
	}
	b, err := json.MarshalIndent(shape, "", "  ")
	if err != nil {
		return "", fmt.Errorf("encode JSON: %w", err)
	}
	return string(b) + "\n", nil
}

// formatConfig is the testable inner of runConfig — separated so we
// can assert on the rendered string without capturing stdout.
func formatConfig(cfg *config.Config) string {
	var b strings.Builder
	fmt.Fprintf(&b, "  config:        %s\n", config.ConfigPath())
	fmt.Fprintln(&b)
	fmt.Fprintln(&b, "  [api]")
	fmt.Fprintf(&b, "    base_url:    %s\n", cfg.API.BaseURL)
	fmt.Fprintln(&b)
	fmt.Fprintln(&b, "  [ui]")
	fmt.Fprintf(&b, "    base_url:    %s\n", cfg.UI.BaseURL)
	fmt.Fprintln(&b)
	fmt.Fprintln(&b, "  [collector]")
	fmt.Fprintf(&b, "    poll_interval_sec:   %d\n", cfg.Collector.PollIntervalSec)
	fmt.Fprintf(&b, "    flush_interval_sec:  %d\n", cfg.Collector.FlushIntervalSec)
	return b.String()
}
