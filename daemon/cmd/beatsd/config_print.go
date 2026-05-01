package main

import (
	"fmt"
	"strings"

	"github.com/ahmedElghable/beats/daemon/internal/config"
)

// runConfig prints the loaded daemon configuration in a human-readable
// shape. Useful when something feels off — `beatsd open` opens the
// wrong URL, the collector seems stuck on a stale interval — and the
// user wants to confirm what got loaded from disk vs the defaults.
//
// Device token is intentionally NOT printed: it lives in the keychain,
// not in this config struct, and even if it did the value is a
// credential the user shouldn't paste into screenshots / Claude
// pastes that this command's output is likely to land in.
func runConfig(cfg *config.Config) error {
	fmt.Print(formatConfig(cfg))
	return nil
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
