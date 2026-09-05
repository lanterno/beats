package collector

import (
	"os/exec"
	"runtime"
	"strconv"
	"strings"
)

// IdleSeconds returns the number of seconds since the last user input event.
// On macOS, uses ioreg. On Linux, uses xprintidle. On Windows, uses
// GetLastInputInfo.
// Returns 0.0 on any error (assumes active).
func IdleSeconds() float64 {
	switch runtime.GOOS {
	case "darwin":
		return idleSecondsMacOS()
	case "linux":
		return idleSecondsLinux()
	case "windows":
		return idleSecondsWindows()
	default:
		return 0.0
	}
}

// maxPlausibleIdleMillis caps what we'll believe from the tick
// subtraction below: ~24.8 days, half the uint32 tick space. Anything
// larger is not a real idle period, it's the two clocks disagreeing.
const maxPlausibleIdleMillis = 1 << 31

// idleSecondsFromTicks computes idle seconds from a 64-bit uptime tick
// count and the 32-bit tick stamp of the last input event.
//
// The subtlety this exists to contain: GetTickCount64 returns
// milliseconds since boot as a uint64, but LASTINPUTINFO.dwTime is a
// uint32 that wraps every ~49.7 days. Truncating the former to uint32
// before subtracting makes the arithmetic wrap in lockstep with the
// latter, so the difference stays correct straight through a
// rollover. Widening dwTime to uint64 instead — the obvious-looking
// alternative — produces a ~49-day idle reading for the first 49 days
// after every wrap.
//
// Extracted from the syscall so the wrap case is testable on any
// platform; you cannot reach a 49-day uptime in a unit test otherwise.
func idleSecondsFromTicks(nowTicks uint64, lastInputTick uint32) float64 {
	idleMs := uint32(nowTicks) - lastInputTick
	if idleMs >= maxPlausibleIdleMillis {
		// Clock anomaly (or lastInput ahead of now by a hair). Assume
		// active, matching this file's behaviour on every other error.
		return 0.0
	}
	return float64(idleMs) / 1000.0
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
