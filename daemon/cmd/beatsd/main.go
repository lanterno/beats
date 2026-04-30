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
	"fmt"
	"os"
	"os/signal"
	"strconv"
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
		editorListener := editor.New()
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
		if err := runDoctor(cfg); err != nil {
			os.Exit(1)
		}

	case "status":
		if err := runStatus(cfg); err != nil {
			os.Exit(1)
		}

	case "recent":
		// Optional flags after the subcommand. We parse inline rather
		// than reaching for the flag package — the option set is small
		// and matches what `beatsd recent --help` would document.
		minutes := 60
		var filter client.FlowWindowsFilter
		for i := 1; i < len(args); i++ {
			switch args[i] {
			case "--minutes":
				if i+1 < len(args) {
					if v, err := strconv.Atoi(args[i+1]); err == nil && v > 0 {
						minutes = v
					}
				}
			case "--repo":
				if i+1 < len(args) {
					filter.EditorRepo = args[i+1]
				}
			case "--language":
				if i+1 < len(args) {
					filter.EditorLanguage = args[i+1]
				}
			case "--bundle":
				if i+1 < len(args) {
					filter.BundleID = args[i+1]
				}
			}
		}
		if err := runRecent(cfg, minutes, filter); err != nil {
			fmt.Fprintf(os.Stderr, "error: %v\n", err)
			os.Exit(1)
		}

	case "version":
		fmt.Print(collectVersionInfo())

	case "unpair":
		if err := pair.DeleteToken(); err != nil {
			fmt.Fprintf(os.Stderr, "error removing token: %v\n", err)
			os.Exit(1)
		}
		fmt.Println("Device token removed from keychain.")

	default:
		fmt.Fprintf(os.Stderr, "unknown command: %s\n", os.Args[1])
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

func printUsage() {
	fmt.Fprintln(os.Stderr, `Usage: beatsd <command> [flags]

Commands:
  pair <code>   Exchange a pairing code for a device token
  run           Start the signal collector daemon
  doctor        Check pairing, API reachability, Accessibility permission, ports
  status        Print whether a daemon is running, timer state, and API reachability
  recent        Print the last hour of flow windows in a small table
                  --minutes N      override the window (default 60)
                  --repo PATH      narrow to a specific editor workspace
                  --language ID    narrow to a VS Code language id (e.g. go, dart)
                  --bundle ID      narrow to a macOS bundle id (e.g. com.microsoft.VSCode)
  unpair        Remove the device token from the keychain
  version       Print version info

Flags:
  --dry-run     Print what would be sent without posting to the API`)
}
