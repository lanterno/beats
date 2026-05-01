package main

import (
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
// false unless --json appears.
type flowFlags struct {
	Minutes int
	Filter  client.FlowWindowsFilter
	AsJSON  bool
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
		case "--json":
			out.AsJSON = true
		}
	}
	return out
}
