package main

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/client"
	"github.com/ahmedElghable/beats/daemon/internal/config"
	"github.com/ahmedElghable/beats/daemon/internal/pair"
)

// runTop fetches the last [minutes] minutes of flow windows and prints
// three small leaderboards — by repo, by language, and by app — mirroring
// the FlowByRepo / FlowByLanguage / FlowByApp cards on the web Insights
// page. Useful at a terminal: "what have I been flowing on, ranked?"
// without switching to the browser.
//
// When `asJSON` is true the leaderboards are emitted as a single JSON
// object keyed by axis ({"by_repo": [...], "by_language": [...],
// "by_app": [...]}) instead of the table — symmetric with `recent
// --json` and `stats --json`, intended for shell pipelines.
func runTop(cfg *config.Config, minutes int, asJSON bool) error {
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

	if asJSON {
		out, err := formatTopJSON(windows)
		if err != nil {
			return err
		}
		fmt.Print(out)
		return nil
	}
	fmt.Print(formatTop(windows, minutes))
	return nil
}

// topJSONOutput is the shape emitted by `beatsd top --json`. Always
// includes all three axes (each may be an empty array) so downstream
// `jq` scripts don't have to guard against missing keys.
type topJSONOutput struct {
	ByRepo     []topBucket `json:"by_repo"`
	ByLanguage []topBucket `json:"by_language"`
	ByApp      []topBucket `json:"by_app"`
}

// formatTopJSON renders the three leaderboards as a JSON object. Empty
// arrays (never null) for missing axes — same rule as
// `formatRecentJSON` since `jq` users would have to special-case null
// otherwise.
func formatTopJSON(windows []client.FlowWindowRecord) (string, error) {
	out := topJSONOutput{
		ByRepo: aggregateBy(windows, func(w client.FlowWindowRecord) string {
			return w.EditorRepo
		}),
		ByLanguage: aggregateBy(windows, func(w client.FlowWindowRecord) string {
			return w.EditorLanguage
		}),
		ByApp: aggregateBy(windows, func(w client.FlowWindowRecord) string {
			// JSON consumers want the raw bundle id (or category fallback),
			// not the human-readable "coding" label that the table form
			// substitutes for terminal readability. Keeping the raw id
			// lets jq filters cross-reference with /flow-windows JSON.
			if w.DominantBundleID != "" {
				return w.DominantBundleID
			}
			return w.DominantCategory
		}),
	}
	if out.ByRepo == nil {
		out.ByRepo = []topBucket{}
	}
	if out.ByLanguage == nil {
		out.ByLanguage = []topBucket{}
	}
	if out.ByApp == nil {
		out.ByApp = []topBucket{}
	}
	b, err := json.MarshalIndent(out, "", "  ")
	if err != nil {
		return "", fmt.Errorf("encode JSON: %w", err)
	}
	return string(b) + "\n", nil
}

// topBucket is one row of a leaderboard. Mirrors the shape used by the
// JS aggregateFlowBy: avg score across the bucket, count of windows
// (≈ tracked minutes since each window is ~1 min). JSON tags match the
// API's TopBucket schema for consistency across the daemon's `top`,
// `stats`, and recent flows.
type topBucket struct {
	Key   string  `json:"key"`
	Avg   float64 `json:"avg"`
	Count int     `json:"count"`
}

// formatTop assembles the three leaderboards into a single string.
// Extracted so it's testable without an HTTP fixture.
func formatTop(windows []client.FlowWindowRecord, minutesRequested int) string {
	if len(windows) == 0 {
		return fmt.Sprintf("  no flow windows in the last %d min — is `beatsd run` up?\n", minutesRequested)
	}

	var b strings.Builder
	fmt.Fprintf(&b, "  last %d min · %d windows\n\n", minutesRequested, len(windows))

	writeLeaderboard(&b, "BY REPO", aggregateBy(windows, func(w client.FlowWindowRecord) string {
		return shortRepoTrail(w.EditorRepo)
	}))
	writeLeaderboard(&b, "BY LANGUAGE", aggregateBy(windows, func(w client.FlowWindowRecord) string {
		return w.EditorLanguage
	}))
	writeLeaderboard(&b, "BY APP", aggregateBy(windows, func(w client.FlowWindowRecord) string {
		// Prefer the human category label ("coding", "browser") and fall
		// back to the bundle id for unknowns. Same logic the table form
		// uses, kept in lockstep so the user sees consistent names.
		return truncOrFallback(w.DominantCategory, w.DominantBundleID, 30)
	}))

	return b.String()
}

// aggregateBy buckets windows by a key extracted via [keyOf], skipping
// empty keys (windows that didn't carry an editor heartbeat in the
// "by repo" / "by language" axes), then returns the top 5 by minutes
// (count). Sort ties resolved by avg score descending so the user sees
// the higher-quality bucket first when minutes match.
func aggregateBy(
	windows []client.FlowWindowRecord,
	keyOf func(client.FlowWindowRecord) string,
) []topBucket {
	type acc struct {
		sum   float64
		count int
	}
	groups := make(map[string]*acc)
	for _, w := range windows {
		k := keyOf(w)
		if k == "" {
			continue
		}
		g, ok := groups[k]
		if !ok {
			g = &acc{}
			groups[k] = g
		}
		g.sum += w.FlowScore
		g.count++
	}

	out := make([]topBucket, 0, len(groups))
	for k, g := range groups {
		out = append(out, topBucket{Key: k, Avg: g.sum / float64(g.count), Count: g.count})
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Count != out[j].Count {
			return out[i].Count > out[j].Count
		}
		return out[i].Avg > out[j].Avg
	})
	if len(out) > 5 {
		out = out[:5]
	}
	return out
}

// writeLeaderboard appends a titled section with one row per bucket.
// Empty buckets render a single helpful "—" line so the section header
// doesn't visually swallow itself.
func writeLeaderboard(b *strings.Builder, title string, rows []topBucket) {
	fmt.Fprintf(b, "  %s\n", title)
	if len(rows) == 0 {
		fmt.Fprintf(b, "    —\n\n")
		return
	}
	for _, r := range rows {
		key := r.Key
		if len(key) > 30 {
			key = key[:29] + "…"
		}
		fmt.Fprintf(b, "    %-30s  %3d  %dm\n", key, int(r.Avg*100), r.Count)
	}
	fmt.Fprintln(b)
}
