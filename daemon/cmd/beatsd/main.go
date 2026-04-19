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

	"github.com/ahmedElghable/beats/daemon/internal/autotimer"
	"github.com/ahmedElghable/beats/daemon/internal/client"
	"github.com/ahmedElghable/beats/daemon/internal/collector"
	"github.com/ahmedElghable/beats/daemon/internal/config"
	"github.com/ahmedElghable/beats/daemon/internal/pair"
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

		runErr := collector.Run(ctx, cfg.Collector, func(w collector.FlowWindow) {
			fmt.Printf("flow: %.2f (coherence=%.2f idle=%.0f%% app=%s cat=%s switches=%d)\n",
				w.FlowScore, w.CoherenceScore, w.IdleFraction*100,
				w.DominantBundleID, w.DominantCategory, w.ContextSwitches)

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
			}
			if postErr := c.PostFlowWindow(ctx, req); postErr != nil {
				fmt.Fprintf(os.Stderr, "post flow window: %v\n", postErr)
			}

			tracker.OnFlowWindow(ctx, w)
		})
		if runErr != nil && runErr != context.Canceled {
			fmt.Fprintf(os.Stderr, "collector error: %v\n", runErr)
			os.Exit(1)
		}

	case "version":
		fmt.Printf("beatsd %s\n", version)

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

func printUsage() {
	fmt.Fprintln(os.Stderr, `Usage: beatsd <command> [flags]

Commands:
  pair <code>   Exchange a pairing code for a device token
  run           Start the signal collector daemon
  unpair        Remove the device token from the keychain
  version       Print version info

Flags:
  --dry-run     Print what would be sent without posting to the API`)
}
