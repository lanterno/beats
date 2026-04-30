package main

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/client"
	"github.com/ahmedElghable/beats/daemon/internal/config"
	"github.com/ahmedElghable/beats/daemon/internal/pair"
)

// runRecent prints the last [minutes] minutes of flow windows in a small
// table. Complements `beatsd status` (right-now snapshot) and `beatsd
// doctor` (setup health) — this answers "what has the daemon actually
// been seeing the last hour?" without the user firing up the web UI.
func runRecent(cfg *config.Config, minutes int) error {
	if minutes <= 0 {
		minutes = 60
	}

	token, err := pair.LoadToken()
	if err != nil {
		return fmt.Errorf("keychain read failed: %w", err)
	}
	if token == "" {
		return fmt.Errorf("not paired — run `beatsd pair <code>`")
	}

	c := client.New(cfg.API.BaseURL, token)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	end := time.Now().UTC()
	start := end.Add(-time.Duration(minutes) * time.Minute)
	windows, err := c.GetFlowWindows(ctx, start, end)
	if err != nil {
		return err
	}

	fmt.Print(formatRecentTable(windows, minutes))
	return nil
}

// formatRecentTable renders a slice of flow windows as a small text table.
// Extracted from runRecent so it can be unit-tested without spinning up
// HTTP. The table is intentionally human-readable (not JSON) — the goal
// is glanceability in a terminal, not machine consumption.
func formatRecentTable(windows []client.FlowWindowRecord, minutesRequested int) string {
	if len(windows) == 0 {
		return fmt.Sprintf("  no flow windows in the last %d min — is `beatsd run` up?\n", minutesRequested)
	}

	var b strings.Builder
	fmt.Fprintf(&b, "  last %d min · %d windows\n\n", minutesRequested, len(windows))
	fmt.Fprintf(&b, "  %-5s  %-3s  %-22s  %s\n", "TIME", "FLOW", "APP", "REPO")
	fmt.Fprintf(&b, "  %s\n", strings.Repeat("─", 60))

	// API returns windows sorted by window_start ASC. Print in the same
	// order so the most recent line lands at the bottom of the terminal —
	// natural reading order when the next thing the user does is keep
	// typing in their shell.
	for _, w := range windows {
		t := w.WindowStart.Local()
		hh := fmt.Sprintf("%02d:%02d", t.Hour(), t.Minute())
		score := fmt.Sprintf("%3d", int(w.FlowScore*100))
		app := truncOrFallback(w.DominantCategory, w.DominantBundleID, 22)
		repo := shortRepoTrail(w.EditorRepo)
		fmt.Fprintf(&b, "  %-5s  %-3s  %-22s  %s\n", hh, score, app, repo)
	}
	return b.String()
}

// truncOrFallback prefers the human category (e.g. "coding") and falls
// back to the bundle id when category is empty. Caps at width.
func truncOrFallback(primary, fallback string, width int) string {
	s := primary
	if s == "" {
		s = fallback
	}
	if s == "" {
		return "—"
	}
	if len(s) > width {
		return s[:width-1] + "…"
	}
	return s
}

// shortRepoTrail returns the last two path segments of an editor_repo so
// a 60-char workspace doesn't blow out the table row. Empty for windows
// without an editor heartbeat.
func shortRepoTrail(p string) string {
	if p == "" {
		return ""
	}
	parts := strings.FieldsFunc(p, func(r rune) bool { return r == '/' || r == '\\' })
	if len(parts) <= 2 {
		return p
	}
	return strings.Join(parts[len(parts)-2:], "/")
}
