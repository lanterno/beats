package main

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/client"
	"github.com/ahmedElghable/beats/daemon/internal/config"
)

// parseStartArgs splits the `start` command's trailing arguments (args
// AFTER the "start" verb) into a project hint and the --json flag. Non-flag
// tokens are joined with a space so `beatsd start side project` works
// without quoting.
func parseStartArgs(args []string) (hint string, asJSON bool) {
	var parts []string
	for _, a := range args {
		if a == "--json" {
			asJSON = true
			continue
		}
		parts = append(parts, a)
	}
	return strings.TrimSpace(strings.Join(parts, " ")), asJSON
}

// hasJSONArg reports whether --json appears in args.
func hasJSONArg(args []string) bool {
	for _, a := range args {
		if a == "--json" {
			return true
		}
	}
	return false
}

// resolveProject picks the active project that best matches hint, trying
// progressively looser tiers: exact (case-insensitive) name, then a unique
// prefix, then a unique substring. Archived projects are ignored — you
// don't start a timer on an archived project. Returns an error when nothing
// matches (with a Levenshtein "did you mean") or when a tier is ambiguous
// (listing the candidates), so the CLI never silently starts the wrong one.
func resolveProject(hint string, projects []client.Project) (client.Project, error) {
	q := strings.ToLower(strings.TrimSpace(hint))
	if q == "" {
		return client.Project{}, fmt.Errorf("no project specified")
	}

	active := make([]client.Project, 0, len(projects))
	for _, p := range projects {
		if !p.Archived {
			active = append(active, p)
		}
	}
	if len(active) == 0 {
		return client.Project{}, fmt.Errorf("no active projects to start")
	}

	// Tier 1: exact name (case-insensitive).
	if m := filterProjects(active, func(n string) bool { return n == q }); len(m) == 1 {
		return m[0], nil
	} else if len(m) > 1 {
		return client.Project{}, ambiguousErr(hint, m)
	}

	// Tier 2: unique prefix.
	if m := filterProjects(active, func(n string) bool { return strings.HasPrefix(n, q) }); len(m) == 1 {
		return m[0], nil
	} else if len(m) > 1 {
		return client.Project{}, ambiguousErr(hint, m)
	}

	// Tier 3: unique substring.
	if m := filterProjects(active, func(n string) bool { return strings.Contains(n, q) }); len(m) == 1 {
		return m[0], nil
	} else if len(m) > 1 {
		return client.Project{}, ambiguousErr(hint, m)
	}

	// No match — nearest by edit distance as a "did you mean".
	best, bestDist := "", -1
	for _, p := range active {
		if d := levenshtein(q, strings.ToLower(p.Name)); bestDist == -1 || d < bestDist {
			bestDist, best = d, p.Name
		}
	}
	return client.Project{}, fmt.Errorf("no project matches %q (did you mean %q?)", hint, best)
}

func filterProjects(projects []client.Project, pred func(loweredName string) bool) []client.Project {
	var out []client.Project
	for _, p := range projects {
		if pred(strings.ToLower(p.Name)) {
			out = append(out, p)
		}
	}
	return out
}

func ambiguousErr(hint string, matches []client.Project) error {
	names := make([]string, 0, len(matches))
	for _, p := range matches {
		names = append(names, p.Name)
	}
	sort.Strings(names)
	return fmt.Errorf("%q matches multiple projects: %s — be more specific", hint, strings.Join(names, ", "))
}

// formatStartResult renders the outcome of a `start`.
func formatStartResult(p client.Project, asJSON bool) string {
	if asJSON {
		b, _ := json.Marshal(map[string]any{
			"action":       "start",
			"project_id":   p.ID,
			"project_name": p.Name,
		})
		return string(b)
	}
	return fmt.Sprintf("Started %s", p.Name)
}

// beatMinutes is the whole-minute duration of a stopped beat, computed from
// its span (robust to however the API serializes the `duration` field).
// Clamps a missing or negative span to 0.
func beatMinutes(b *client.StoppedBeat) int {
	if b == nil || b.Start.IsZero() || b.End.IsZero() {
		return 0
	}
	d := b.End.Sub(b.Start)
	if d < 0 {
		return 0
	}
	return int(d.Minutes())
}

// formatStopResult renders the outcome of a `stop`.
func formatStopResult(b *client.StoppedBeat, asJSON bool) string {
	mins := beatMinutes(b)
	if asJSON {
		out, _ := json.Marshal(map[string]any{
			"action":           "stop",
			"duration_minutes": mins,
		})
		return string(out)
	}
	return fmt.Sprintf("Stopped — logged %dm", mins)
}

// runStart implements `beatsd start <project> [--json]`: resolve the hint to
// a project, then start its timer (server stamps the time).
func runStart(cfg *config.Config, args []string) error {
	hint, asJSON := parseStartArgs(args[1:])
	if hint == "" {
		return fmt.Errorf("usage: beatsd start <project>")
	}
	c, ctx, cancel, err := authedClient(cfg, 10*time.Second)
	if err != nil {
		return err
	}
	defer cancel()

	projects, err := c.GetProjects(ctx)
	if err != nil {
		return err
	}
	p, err := resolveProject(hint, projects)
	if err != nil {
		return err
	}
	if err := c.StartTimer(ctx, p.ID); err != nil {
		return err
	}
	fmt.Println(formatStartResult(p, asJSON))
	return nil
}

// runStop implements `beatsd stop [--json]`: stop the running timer and
// report the logged duration.
func runStop(cfg *config.Config, args []string) error {
	asJSON := hasJSONArg(args[1:])
	c, ctx, cancel, err := authedClient(cfg, 10*time.Second)
	if err != nil {
		return err
	}
	defer cancel()

	b, err := c.StopTimer(ctx)
	if err != nil {
		return err
	}
	fmt.Println(formatStopResult(b, asJSON))
	return nil
}
