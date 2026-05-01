package main

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/bundle"
	"github.com/ahmedElghable/beats/daemon/internal/client"
	"github.com/ahmedElghable/beats/daemon/internal/config"
)

// runRecent prints the last [minutes] minutes of flow windows. Complements
// `beatsd status` (right-now snapshot) and `beatsd doctor` (setup health)
// — this answers "what has the daemon actually been seeing the last
// hour?" without the user firing up the web UI.
//
// `filter` narrows the result to a specific repo / language / app via
// the same query params the web Insights cards use. The table caption
// surfaces whichever filters were applied so the user can tell at a
// glance which slice they're looking at.
//
// When `asJSON` is true, the windows are emitted as a JSON array on
// stdout instead of the human table. Intended for shell scripting:
// `beatsd recent --language go --json | jq '.[] | select(.flow_score > 0.7)'`
// — the table form prints decorative captions that would corrupt jq input.
func runRecent(cfg *config.Config, minutes int, filter client.FlowWindowsFilter, asJSON bool) error {
	if minutes <= 0 {
		minutes = 60
	}

	c, ctx, cancel, err := authedClient(cfg, 10*time.Second)
	if err != nil {
		return err
	}
	defer cancel()

	end := time.Now().UTC()
	start := end.Add(-time.Duration(minutes) * time.Minute)
	windows, err := c.GetFlowWindowsFiltered(ctx, start, end, filter)
	if err != nil {
		return err
	}

	if asJSON {
		out, err := formatRecentJSON(windows)
		if err != nil {
			return err
		}
		fmt.Print(out)
		return nil
	}
	fmt.Print(formatRecentTable(windows, minutes, filter))
	return nil
}

// formatRecentJSON renders the windows as a pretty-printed JSON array.
// Always emits an array (even when empty) so callers piping through `jq`
// don't have to special-case "no rows" — `[]` is valid JSON, `null` would
// surprise tools that expect to iterate. Trailing newline so terminal
// prompts land on the next line.
func formatRecentJSON(windows []client.FlowWindowRecord) (string, error) {
	if windows == nil {
		windows = []client.FlowWindowRecord{}
	}
	b, err := json.MarshalIndent(windows, "", "  ")
	if err != nil {
		return "", fmt.Errorf("encode JSON: %w", err)
	}
	return string(b) + "\n", nil
}

// formatRecentTable renders a slice of flow windows as a small text table.
// Extracted from runRecent so it can be unit-tested without spinning up
// HTTP. The table is intentionally human-readable (not JSON) — the goal
// is glanceability in a terminal, not machine consumption.
func formatRecentTable(
	windows []client.FlowWindowRecord,
	minutesRequested int,
	filter client.FlowWindowsFilter,
) string {
	if len(windows) == 0 {
		hint := "is `beatsd run` up?"
		if !filterIsEmpty(filter) {
			// Don't blame the daemon when the user just narrowed the slice
			// to nothing. The unfiltered set might be fine.
			hint = "no rows for the active filter — try widening or dropping it"
		}
		return fmt.Sprintf("  no flow windows in the last %d min — %s\n", minutesRequested, hint)
	}

	var b strings.Builder
	if caption := filterCaption(filter); caption != "" {
		fmt.Fprintf(&b, "  last %d min · %d windows · %s\n\n", minutesRequested, len(windows), caption)
	} else {
		fmt.Fprintf(&b, "  last %d min · %d windows\n\n", minutesRequested, len(windows))
	}
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
		app := truncOrFallback(w.DominantCategory, bundle.ShortLabel(w.DominantBundleID), 22)
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

// filterIsEmpty reports whether no narrow filter is active. Used to pick
// the right empty-state hint — "is the daemon up?" vs "your filter
// matched nothing".
func filterIsEmpty(f client.FlowWindowsFilter) bool {
	return f.EditorRepo == "" && f.EditorLanguage == "" && f.BundleID == ""
}

// filterCaption builds a single human-readable line summarizing the
// active filter (if any). Joined into the table header so the user can
// see at a glance which slice they're staring at.
func filterCaption(f client.FlowWindowsFilter) string {
	var parts []string
	if f.EditorRepo != "" {
		parts = append(parts, "repo="+shortRepoTrail(f.EditorRepo))
	}
	if f.EditorLanguage != "" {
		parts = append(parts, "lang="+f.EditorLanguage)
	}
	if f.BundleID != "" {
		parts = append(parts, "app="+f.BundleID)
	}
	return strings.Join(parts, " · ")
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
