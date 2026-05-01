package main

import (
	"fmt"
	"strconv"

	"github.com/ahmedElghable/beats/daemon/internal/client"
)

// flowFlags holds the parsed flag state shared by the recent / stats /
// top subcommands. They all want some subset of {minutes, filter, json}
// so we parse them once in parseFlowFlags and let each call site read
// only the fields it cares about.
//
// `Minutes` defaults to 60 when --minutes is absent or non-positive.
// `Filter` is zero-valued when no filter flag is set. `AsJSON` is
// false unless --json appears. `Here` is true when --here appeared;
// callers resolve it to a repo path via applyHereFlag at dispatch
// time (kept out of parseFlowFlags so the parser stays pure — it
// doesn't shell out to git).
type flowFlags struct {
	Minutes int
	Filter  client.FlowWindowsFilter
	AsJSON  bool
	Here    bool
	// Limit caps leaderboard rows in `beatsd top`; 0 means "use the
	// command default" (5). Only `top` reads this — recent and stats
	// either return all rows in the window or a single summary, so
	// limit doesn't apply there.
	Limit int
}

// parseFlowFlags walks a slice of subcommand arguments and pulls out the
// shared flag set. Unknown flags are silently ignored — same behavior as
// the inline parsing the dispatch arms used to do, kept intentionally so
// future flags can be added in one place without breaking callers that
// happen to pass them through.
//
// Skipping starts at index 1 because args[0] is the subcommand name
// (e.g. "recent"). A caller passing a clean flag-only slice can pass
// args directly; this matches the existing `args := os.Args[1:]` shape
// in main.go.
func parseFlowFlags(args []string) flowFlags {
	out := flowFlags{Minutes: 60}
	for i := 1; i < len(args); i++ {
		switch args[i] {
		case "--minutes":
			if i+1 < len(args) {
				if v, err := strconv.Atoi(args[i+1]); err == nil && v > 0 {
					out.Minutes = v
				}
			}
		case "--repo":
			if i+1 < len(args) {
				out.Filter.EditorRepo = args[i+1]
			}
		case "--language":
			if i+1 < len(args) {
				out.Filter.EditorLanguage = args[i+1]
			}
		case "--bundle":
			if i+1 < len(args) {
				out.Filter.BundleID = args[i+1]
			}
		case "--here":
			out.Here = true
		case "--limit":
			if i+1 < len(args) {
				if v, err := strconv.Atoi(args[i+1]); err == nil && v > 0 {
					out.Limit = v
				}
			}
		case "--json":
			out.AsJSON = true
		}
	}
	return out
}

// applyHereFlag resolves the --here shorthand to a concrete repo
// path on the filter, mirroring the same logic `beatsd open --here`
// uses (gitToplevel(cwd) → falls back to cwd). When --here was not
// passed, returns the input unchanged.
//
// Errors out if both --here and --repo were set — the same flag
// would target the same field, so one of them is ambiguous noise
// rather than a meaningful AND.
func applyHereFlag(f flowFlags) (flowFlags, error) {
	if !f.Here {
		return f, nil
	}
	if f.Filter.EditorRepo != "" {
		return f, fmt.Errorf("--here and --repo are mutually exclusive")
	}
	repo, err := resolveHereRepo()
	if err != nil {
		return f, err
	}
	f.Filter.EditorRepo = repo
	return f, nil
}
