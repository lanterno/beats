// beatsd is the Beats ambient daemon.
//
// Usage:
//
//	beatsd pair <code>    Exchange a pairing code for a device token
//	beatsd run            Start the signal collector daemon
//	beatsd version        Print version info
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/signal"
	"sync/atomic"
	"time"

	"github.com/ahmedElghable/beats/daemon/internal/autotimer"
	"github.com/ahmedElghable/beats/daemon/internal/client"
	"github.com/ahmedElghable/beats/daemon/internal/collector"
	"github.com/ahmedElghable/beats/daemon/internal/config"
	"github.com/ahmedElghable/beats/daemon/internal/editor"
	"github.com/ahmedElghable/beats/daemon/internal/pair"
	"github.com/ahmedElghable/beats/daemon/internal/shield"
)

var version = "dev"

func main() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	// Help is recognized BEFORE config loads — a user just looking
	// for usage shouldn't fail because daemon.toml is missing or
	// malformed. Exit 0 because asking for help isn't an error.
	//
	// `--help` / `-h` are recognized in any position so that
	// `beatsd recent --help` and `beatsd run --help` work. The
	// previous implementation only matched the first arg, so per-
	// command help silently fell through to actually executing
	// the command (which then failed on "not paired" or similar).
	if hasHelpFlag(os.Args[1:]) {
		printHelp()
		return
	}

	cfg, err := config.Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "error loading config: %v\n", err)
		os.Exit(1)
	}

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()

	// Check for --dry-run flag
	dryRun := false
	args := os.Args[1:]
	for i, arg := range args {
		if arg == "--dry-run" {
			dryRun = true
			args = append(args[:i], args[i+1:]...)
			break
		}
	}
	if len(args) == 0 {
		printUsage()
		os.Exit(1)
	}

	switch args[0] {
	case "pair":
		if len(args) < 2 {
			fmt.Fprintln(os.Stderr, "usage: beatsd pair <code>")
			os.Exit(1)
		}
		code := args[1]
		deviceName, _ := os.Hostname()

		c := client.New(cfg.API.BaseURL, "")
		deviceID, err := pair.Run(ctx, c, code, deviceName)
		if err != nil {
			fmt.Fprintf(os.Stderr, "pairing failed: %v\n", err)
			os.Exit(1)
		}
		fmt.Printf("Paired successfully. Device ID: %s\n", deviceID)
		fmt.Printf("Token stored in OS keychain.\n")

	case "run":
		if dryRun {
			fmt.Printf("beatsd %s — DRY RUN (no data will be sent)\n", version)
		} else {
			token, err := pair.LoadToken()
			if err != nil {
				fmt.Fprintf(os.Stderr, "error loading device token: %v\n", err)
				os.Exit(1)
			}
			if token == "" {
				fmt.Fprintln(os.Stderr, "not paired. Run 'beatsd pair <code>' first.")
				os.Exit(1)
			}
			cfg.API.DeviceToken = token
		}

		c := client.New(cfg.API.BaseURL, cfg.API.DeviceToken)
		if !dryRun {
			fmt.Printf("beatsd %s — daemon running (API: %s)\n", version, cfg.API.BaseURL)
			if err := c.PostHeartbeat(ctx); err != nil {
				fmt.Fprintf(os.Stderr, "warning: initial heartbeat failed: %v\n", err)
			}
		}

		tracker := autotimer.NewTracker(c)

		// Editor heartbeat listener — receives beats from integrations like
		// the VS Code extension and exposes the most recent one to the
		// collector via Latest(). Failure to bind (e.g. port already in use)
		// is non-fatal: the collector keeps working without editor context.
		editorListener := editor.New(version)
		// Wire a SummaryFetcher so editor extensions can probe today's
		// flow stats via the loopback listener without standing up
		// their own auth. Returns the API response bytes verbatim.
		editorListener.SetSummaryFetcher(func(fctx context.Context) ([]byte, error) {
			now := time.Now().UTC()
			start := time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, time.UTC)
			s, err := c.GetFlowWindowsSummary(fctx, start, now, client.FlowWindowsFilter{})
			if err != nil {
				return nil, err
			}
			return json.Marshal(s)
		})
		if err := editorListener.Start(ctx, editor.DefaultPort); err != nil {
			fmt.Fprintf(os.Stderr, "warning: editor listener: %v\n", err)
		}
		defer func() { _ = editorListener.Stop() }()

		// Distraction shield: detects drift into known time-sink apps while
		// a timer is running and emits a system notification + log. Needs
		// to know whether a timer is running on each sample; we cache that
		// state from the API on a 30s poller (cheap; the user starts/stops
		// timers rarely). atomic.Bool keeps the read on the hot path lock-
		// free.
		var timerRunning atomic.Bool
		if !dryRun {
			go pollTimerContext(ctx, c, &timerRunning)
		}
		shieldTracker := shield.NewTracker(func(ev shield.DriftEvent) {
			fmt.Printf("drift: %s for %s\n", ev.BundleID, ev.Duration.Round(time.Second))
		})

		runErr := collector.Run(ctx, cfg.Collector, func(w collector.FlowWindow) {
			if hb := editorListener.Latest(); hb != nil {
				w.EditorRepo = hb.Repo
				w.EditorBranch = hb.Branch
				w.EditorLanguage = hb.Language
			}

			fmt.Printf("flow: %.2f (coherence=%.2f idle=%.0f%% app=%s cat=%s switches=%d repo=%s)\n",
				w.FlowScore, w.CoherenceScore, w.IdleFraction*100,
				w.DominantBundleID, w.DominantCategory, w.ContextSwitches,
				shortRepo(w.EditorRepo))

			if dryRun {
				return // Don't send anything in dry-run mode
			}

			req := client.FlowWindowRequest{
				WindowStart:      w.WindowStart,
				WindowEnd:        w.WindowEnd,
				FlowScore:        w.FlowScore,
				CadenceScore:     w.CadenceScore,
				CoherenceScore:   w.CoherenceScore,
				CategoryFitScore: w.CategoryFitScore,
				IdleFraction:     w.IdleFraction,
				DominantBundleID: w.DominantBundleID,
				DominantCategory: w.DominantCategory,
				ContextSwitches:  w.ContextSwitches,
				ActiveProjectID:  w.ActiveProjectID,
				EditorRepo:       w.EditorRepo,
				EditorBranch:     w.EditorBranch,
				EditorLanguage:   w.EditorLanguage,
			}
			if postErr := c.PostFlowWindow(ctx, req); postErr != nil {
				fmt.Fprintf(os.Stderr, "post flow window: %v\n", postErr)
			} else {
				// Record the success so /health's windows_emitted
				// counter reflects only actually-landed windows.
				editorListener.RecordWindowEmitted()
			}

			tracker.OnFlowWindow(ctx, w)
		}, func(s collector.Sample) {
			shieldTracker.OnSample(s, timerRunning.Load())
		})
		if runErr != nil && runErr != context.Canceled {
			fmt.Fprintf(os.Stderr, "collector error: %v\n", runErr)
			os.Exit(1)
		}

	case "doctor":
		var asJSON bool
		for i := 1; i < len(args); i++ {
			if args[i] == "--json" {
				asJSON = true
			}
		}
		if err := runDoctor(cfg, asJSON); err != nil {
			os.Exit(1)
		}

	case "status":
		var asJSON bool
		for i := 1; i < len(args); i++ {
			if args[i] == "--json" {
				asJSON = true
			}
		}
		if err := runStatus(cfg, asJSON); err != nil {
			os.Exit(1)
		}

	case "recent":
		f, err := applyHereFlag(parseFlowFlags(args))
		if err != nil {
			fmt.Fprintf(os.Stderr, "error: %v\n", err)
			os.Exit(1)
		}
		if err := runRecent(cfg, f.Minutes, f.Filter, f.AsJSON); err != nil {
			fmt.Fprintf(os.Stderr, "error: %v\n", err)
			os.Exit(1)
		}

	case "stats":
		f, err := applyHereFlag(parseFlowFlags(args))
		if err != nil {
			fmt.Fprintf(os.Stderr, "error: %v\n", err)
			os.Exit(1)
		}
		if err := runStats(cfg, f.Minutes, f.Filter, f.AsJSON); err != nil {
			fmt.Fprintf(os.Stderr, "error: %v\n", err)
			os.Exit(1)
		}

	case "top":
		// `top` honors the same flag set as `recent` / `stats`. Cross-
		// axis filtering is genuinely useful: filter by language and
		// the by-repo / by-app leaderboards still answer "where do I
		// flow best when writing Go?" — same affordance the web cards
		// give when you click a chip.
		f, err := applyHereFlag(parseFlowFlags(args))
		if err != nil {
			fmt.Fprintf(os.Stderr, "error: %v\n", err)
			os.Exit(1)
		}
		if err := runTop(cfg, f.Minutes, f.Filter, f.AsJSON); err != nil {
			fmt.Fprintf(os.Stderr, "error: %v\n", err)
			os.Exit(1)
		}

	case "open":
		// Optional --repo / --language / --bundle to deep-link a
		// filtered view (mirrors the chip filters on the web Insights
		// page; all three AND-compose). --here is shorthand for
		// `--repo $(git rev-parse --show-toplevel)`, useful from any
		// subdir of a paired workspace. --print writes the URL to
		// stdout instead of launching a browser, useful for shell
		// pipelines and headless setups.
		var filter OpenFilter
		var printOnly, useHere bool
		for i := 1; i < len(args); i++ {
			switch args[i] {
			case "--repo":
				if i+1 < len(args) {
					filter.Repo = args[i+1]
				}
			case "--language":
				if i+1 < len(args) {
					filter.Language = args[i+1]
				}
			case "--bundle":
				if i+1 < len(args) {
					filter.Bundle = args[i+1]
				}
			case "--here":
				useHere = true
			case "--print":
				printOnly = true
			}
		}
		if useHere {
			if filter.Repo != "" {
				fmt.Fprintln(os.Stderr, "error: --here and --repo are mutually exclusive")
				os.Exit(1)
			}
			repo, err := resolveHereRepo()
			if err != nil {
				fmt.Fprintf(os.Stderr, "error: %v\n", err)
				os.Exit(1)
			}
			filter.Repo = repo
		}
		if err := runOpen(cfg, filter, printOnly); err != nil {
			fmt.Fprintf(os.Stderr, "error: %v\n", err)
			os.Exit(1)
		}

	case "config":
		var asJSON bool
		for i := 1; i < len(args); i++ {
			if args[i] == "--json" {
				asJSON = true
			}
		}
		if err := runConfig(cfg, asJSON); err != nil {
			fmt.Fprintf(os.Stderr, "error: %v\n", err)
			os.Exit(1)
		}

	case "version":
		var asJSON bool
		for i := 1; i < len(args); i++ {
			if args[i] == "--json" {
				asJSON = true
			}
		}
		v := collectVersionInfo()
		if asJSON {
			out, err := formatVersionJSON(v)
			if err != nil {
				fmt.Fprintf(os.Stderr, "error: %v\n", err)
				os.Exit(1)
			}
			fmt.Print(out)
		} else {
			fmt.Print(v)
		}

	case "unpair":
		if err := pair.DeleteToken(); err != nil {
			fmt.Fprintf(os.Stderr, "error removing token: %v\n", err)
			os.Exit(1)
		}
		fmt.Println("Device token removed from keychain.")

	default:
		fmt.Fprintf(os.Stderr, "unknown command: %s\n", args[0])
		if suggestion := suggestCommand(args[0]); suggestion != "" {
			fmt.Fprintf(os.Stderr, "did you mean `%s`?\n", suggestion)
		}
		printUsage()
		os.Exit(1)
	}
}

// pollTimerContext keeps `running` in sync with whether the user has an
// active timer on the API side. Runs until ctx is cancelled. Failures (API
// down, bad token) are logged once per minute at most so a flaky network
// doesn't flood stderr.
func pollTimerContext(ctx context.Context, c *client.Client, running *atomic.Bool) {
	const interval = 30 * time.Second
	tick := time.NewTicker(interval)
	defer tick.Stop()

	var lastErrLog time.Time

	check := func() {
		ctx2, cancel := context.WithTimeout(ctx, 5*time.Second)
		defer cancel()
		tc, err := c.GetTimerContext(ctx2)
		if err != nil {
			if time.Since(lastErrLog) > time.Minute {
				fmt.Fprintf(os.Stderr, "timer-context poll: %v\n", err)
				lastErrLog = time.Now()
			}
			return
		}
		running.Store(tc.TimerRunning)
	}

	check() // immediate so we don't wait 30s for the first signal
	for {
		select {
		case <-ctx.Done():
			return
		case <-tick.C:
			check()
		}
	}
}

// shortRepo returns the basename of a repo path for the log line so a
// 60-char workspace doesn't blow out the terminal.
func shortRepo(p string) string {
	if p == "" {
		return "-"
	}
	if i := lastSlash(p); i >= 0 && i < len(p)-1 {
		return p[i+1:]
	}
	return p
}

func lastSlash(s string) int {
	for i := len(s) - 1; i >= 0; i-- {
		if s[i] == '/' || s[i] == '\\' {
			return i
		}
	}
	return -1
}

// hasHelpFlag reports whether any of the args is `--help`, `-h`, or
// the bare `help` subcommand. Recognized in any position so per-
// command help (e.g. `beatsd recent --help`) routes to the same
// usage text the global form prints — without it, the recent
// dispatch arm would just execute, ignore the unknown flag, and
// fail with "not paired" or similar, leaving the user wondering.
func hasHelpFlag(args []string) bool {
	for _, a := range args {
		if a == "--help" || a == "-h" || a == "help" {
			return true
		}
	}
	return false
}

// knownCommands is the canonical list of dispatch arms recognized
// by main(). Kept in sync by hand — adding a command here without
// also adding a switch case is harmless (suggestCommand just
// returns the name and the user gets "unknown command" anyway).
var knownCommands = []string{
	"pair", "run", "doctor", "status",
	"recent", "stats", "top", "open",
	"version", "config", "unpair",
}

// suggestCommand returns the closest known command name to [input]
// if the edit distance is small enough to be a plausible typo.
// Returns "" when no good match exists.
//
// Two rules:
//
//  1. Hard cap at distance ≤ 2 (catches the realistic typos:
//     "dotcor", "recnet", transposed pairs).
//  2. Distance must be strictly less than len(input) — short
//     inputs need short edits to qualify. Without this rule a
//     2-char input like "do" would suggest "top" (distance 2),
//     which feels like a wild guess rather than a useful nudge.
//
// On ties, prefer the candidate whose length is closest to the
// input — "stauts" (len 6) gets "status" (also 6, distance 2)
// over "stats" (len 5, distance 1) because the equal-length
// match is the more likely intent.
func suggestCommand(input string) string {
	const maxDistance = 2
	if input == "" {
		return ""
	}
	best := ""
	bestDist := maxDistance + 1
	bestLenDiff := 0
	for _, cmd := range knownCommands {
		d := levenshtein(input, cmd)
		if d > maxDistance || d >= len(input) {
			continue
		}
		lenDiff := absInt(len(cmd) - len(input))
		// Prefer lower distance; tie-break on smaller length
		// difference (more likely the intended command).
		if d < bestDist || (d == bestDist && lenDiff < bestLenDiff) {
			best = cmd
			bestDist = d
			bestLenDiff = lenDiff
		}
	}
	return best
}

func absInt(x int) int {
	if x < 0 {
		return -x
	}
	return x
}

// levenshtein computes the edit distance between two strings using
// the standard dynamic-programming recurrence — minimal allocs,
// O(len(a)*len(b)) time. Pure stdlib so we don't pull in a
// fuzzy-match dep just for the typo-suggestion path.
func levenshtein(a, b string) int {
	ra := []rune(a)
	rb := []rune(b)
	if len(ra) == 0 {
		return len(rb)
	}
	if len(rb) == 0 {
		return len(ra)
	}
	prev := make([]int, len(rb)+1)
	curr := make([]int, len(rb)+1)
	for j := range prev {
		prev[j] = j
	}
	for i := 1; i <= len(ra); i++ {
		curr[0] = i
		for j := 1; j <= len(rb); j++ {
			cost := 1
			if ra[i-1] == rb[j-1] {
				cost = 0
			}
			curr[j] = minInt(
				prev[j]+1,      // deletion
				curr[j-1]+1,    // insertion
				prev[j-1]+cost, // substitution
			)
		}
		prev, curr = curr, prev
	}
	return prev[len(rb)]
}

func minInt(a, b, c int) int {
	m := a
	if b < m {
		m = b
	}
	if c < m {
		m = c
	}
	return m
}

// printUsage writes the help text to stderr — used by error paths
// (no command, unknown command). For an explicit help request use
// printHelp, which writes to stdout so a `beatsd --help | grep` works.
func printUsage() { writeUsage(os.Stderr) }
func printHelp()  { writeUsage(os.Stdout) }

func writeUsage(out *os.File) {
	fmt.Fprintln(out, `Usage: beatsd <command> [flags]

Commands:
  pair <code>   Exchange a pairing code for a device token
  run           Start the signal collector daemon
                  --dry-run        print computed flow windows without posting to the API
  doctor        Check pairing, API reachability, Accessibility permission, ports
                  --json           emit the report as a JSON object (for piping into jq)
  status        Print whether a daemon is running, timer state, and API reachability
                  --json           emit the report as a JSON object (for piping into jq)
  recent        Print the last hour of flow windows in a small table
                  --minutes N      override the window (default 60)
                  --repo PATH      narrow to a specific editor workspace
                  --here           shorthand for --repo $(git rev-parse --show-toplevel)
                  --language ID    narrow to a VS Code language id (e.g. go, dart)
                  --bundle ID      narrow to a macOS bundle id (e.g. com.microsoft.VSCode)
                  --json           emit raw windows as a JSON array (for piping into jq)
  top           Print top-5 leaderboards by repo / language / app for the recent window
                  --minutes N      override the window (default 60)
                  --repo PATH      narrow to a specific editor workspace
                  --here           shorthand for --repo $(git rev-parse --show-toplevel)
                  --language ID    narrow to a VS Code language id (e.g. go, dart)
                  --bundle ID      narrow to a macOS bundle id (e.g. com.microsoft.VSCode)
                  --json           emit the three leaderboards as a JSON object (for piping into jq)
  open          Open the Beats web UI Insights page in the system browser
                  --repo PATH      deep-link by editor workspace (?repo=…)
                  --here           shorthand for --repo $(git rev-parse --show-toplevel)
                  --language ID    deep-link by VS Code language id (?language=…)
                  --bundle ID      deep-link by macOS bundle id (?bundle=…)
                  --print          print the URL to stdout instead of launching
  stats         Print a one-line headline summary (count · avg · peak · best repo)
                  --minutes N      override the window (default 60)
                  --repo PATH      narrow to a specific editor workspace
                  --here           shorthand for --repo $(git rev-parse --show-toplevel)
                  --language ID    narrow to a VS Code language id
                  --bundle ID      narrow to a macOS bundle id
                  --json           emit the FlowWindowSummary object as JSON
  unpair        Remove the device token from the keychain
  version       Print version info
                  --json           emit version + build info as a JSON object (for piping into jq)
  config        Print the loaded daemon config (API + UI URLs, collector intervals)
                  --json           emit as a JSON object (for piping into jq)`)
}
