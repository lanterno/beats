package collector

import (
	"os/exec"
	"runtime"
	"strconv"
	"strings"
)

// IdleSeconds returns the number of seconds since the last user input event.
// On macOS, uses ioreg. On Linux, uses xprintidle.
// Returns 0.0 on any error (assumes active).
func IdleSeconds() float64 {
	switch runtime.GOOS {
	case "darwin":
		return idleSecondsMacOS()
	case "linux":
		return idleSecondsLinux()
	default:
		return 0.0
	}
}

func idleSecondsMacOS() float64 {
	out, err := exec.Command("ioreg", "-c", "IOHIDSystem", "-d", "4").Output()
	if err != nil {
		return 0.0
	}
	return parseIdleTime(string(out))
}

func idleSecondsLinux() float64 {
	// xprintidle outputs idle time in milliseconds
	out, err := exec.Command("xprintidle").Output()
	if err != nil {
		return 0.0
	}
	ms, err := strconv.ParseInt(strings.TrimSpace(string(out)), 10, 64)
	if err != nil {
		return 0.0
	}
	return float64(ms) / 1000.0
}

// parseIdleTime extracts HIDIdleTime from ioreg output and converts nanoseconds to seconds.
// Looks for a line like: "HIDIdleTime" = 1234567890
func parseIdleTime(output string) float64 {
	for _, line := range strings.Split(output, "\n") {
		if !strings.Contains(line, "HIDIdleTime") {
			continue
		}
		// Skip the "HIDIdleTime" key entry (as opposed to value)
		if strings.Contains(line, "=") {
			parts := strings.SplitN(line, "=", 2)
			if len(parts) != 2 {
				continue
			}
			valStr := strings.TrimSpace(parts[1])
			ns, err := strconv.ParseInt(valStr, 10, 64)
			if err != nil {
				continue
			}
			return float64(ns) / 1e9
		}
	}
	return 0.0
}
