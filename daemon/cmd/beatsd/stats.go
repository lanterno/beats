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

// runStats prints a one-line headline summary of the recent flow window
// slice. Hits the API's /flow-windows/summary endpoint so it costs one
// round-trip — designed for shell prompts and status bars where you want
// a quick "how's my flow today?" without firing up the web UI or paging
// through `beatsd recent`.
//
// Honors the same filter flags as `beatsd recent`. With `--json` emits
// the raw FlowWindowSummary as JSON (one object, not an array — different
// from `beatsd recent --json` since this is a single summary not a list).
func runStats(
	cfg *config.Config,
	minutes int,
	filter client.FlowWindowsFilter,
	asJSON bool,
) error {
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
	summary, err := c.GetFlowWindowsSummary(ctx, start, end, filter)
	if err != nil {
		return err
	}

	if asJSON {
		out, err := json.MarshalIndent(summary, "", "  ")
		if err != nil {
			return fmt.Errorf("encode JSON: %w", err)
		}
		fmt.Println(string(out))
		return nil
	}
	fmt.Print(formatStatsLine(summary, minutes, filter))
	return nil
}

// formatStatsLine renders a single line: count · avg · peak · best repo.
// Extracted so it's testable without HTTP. Empty slice gets a friendly
// hint instead of "0 windows · avg 0" — the latter would render as an
// active stat row when there's actually nothing to say.
func formatStatsLine(
	s *client.FlowWindowSummary,
	minutesRequested int,
	filter client.FlowWindowsFilter,
) string {
	if s == nil || s.Count == 0 {
		hint := "is `beatsd run` up?"
		if !filterIsEmpty(filter) {
			hint = "no rows for the active filter — try widening or dropping it"
		}
		return fmt.Sprintf("  no flow windows in the last %d min — %s\n", minutesRequested, hint)
	}

	parts := []string{
		fmt.Sprintf("last %d min", minutesRequested),
		fmt.Sprintf("%d windows", s.Count),
		fmt.Sprintf("avg %d", int(s.Avg*100)),
	}
	parts = append(parts, formatPeakChunk(s))

	// Mention the top axes when present. Repo first because it's the
	// most identifying; app second since the friendly label ("VS Code")
	// is short. Language is omitted from the headline — it adds another
	// chunk without much new info when repo is also shown, and `beatsd
	// top` covers the full picture.
	if s.TopRepo != nil && s.TopRepo.Key != "" {
		parts = append(parts, "best repo: "+shortRepoTrail(s.TopRepo.Key))
	}
	if s.TopBundle != nil && s.TopBundle.Key != "" {
		parts = append(parts, "best app: "+bundle.ShortLabel(s.TopBundle.Key))
	}

	if caption := filterCaption(filter); caption != "" {
		parts = append(parts, caption)
	}

	return "  " + strings.Join(parts, " · ") + "\n"
}

// formatPeakChunk turns the peak score + time into a single readable
// chunk. When PeakAt is nil (only happens with count=0, which the
// caller has already handled) we fall back to just the score so the
// stats line never reads as a malformed sentence.
func formatPeakChunk(s *client.FlowWindowSummary) string {
	score := int(s.Peak * 100)
	if s.PeakAt == nil {
		return fmt.Sprintf("peak %d", score)
	}
	t := s.PeakAt.Local()
	return fmt.Sprintf("peak %d at %02d:%02d", score, t.Hour(), t.Minute())
}
