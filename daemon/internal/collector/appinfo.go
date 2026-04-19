package collector

import (
	"os/exec"
	"runtime"
	"strings"
)

// FrontmostApp returns the bundle ID and name of the frontmost application.
// On macOS, uses lsappinfo. On Linux, uses xdotool + xprop (X11) or
// swaymsg (Wayland). Returns empty strings on any error (graceful degradation).
func FrontmostApp() (bundleID, appName string) {
	switch runtime.GOOS {
	case "darwin":
		return frontmostAppMacOS()
	case "linux":
		return frontmostAppLinux()
	default:
		return "", ""
	}
}

func frontmostAppMacOS() (string, string) {
	frontOut, err := exec.Command("lsappinfo", "front").Output()
	if err != nil {
		return "", ""
	}
	asn := strings.TrimSpace(string(frontOut))
	if asn == "" || asn == "(null)" {
		return "", ""
	}

	infoOut, err := exec.Command("lsappinfo", "info", "-only", "bundleid", "-only", "name", asn).Output()
	if err != nil {
		return "", ""
	}

	return parseLsappinfo(string(infoOut))
}

func frontmostAppLinux() (string, string) {
	// Try swaymsg first (Wayland / Sway)
	if out, err := exec.Command("swaymsg", "-t", "get_tree").Output(); err == nil {
		return parseSwaymsgTree(string(out))
	}

	// Fall back to xdotool (X11)
	winID, err := exec.Command("xdotool", "getactivewindow").Output()
	if err != nil {
		return "", ""
	}
	wid := strings.TrimSpace(string(winID))

	// Get WM_CLASS (used as bundle ID equivalent on Linux)
	classOut, err := exec.Command("xprop", "-id", wid, "WM_CLASS").Output()
	if err != nil {
		return "", ""
	}
	className := parseXpropClass(string(classOut))

	// Get window name
	nameOut, err := exec.Command("xdotool", "getactivewindow", "getwindowname").Output()
	if err != nil {
		return className, ""
	}

	return className, strings.TrimSpace(string(nameOut))
}

// parseXpropClass extracts the class name from xprop WM_CLASS output.
// Format: WM_CLASS(STRING) = "instance", "ClassName"
func parseXpropClass(output string) string {
	parts := strings.SplitN(output, "=", 2)
	if len(parts) != 2 {
		return ""
	}
	fields := strings.Split(parts[1], ",")
	if len(fields) < 2 {
		return strings.Trim(strings.TrimSpace(parts[1]), `" `)
	}
	return strings.Trim(strings.TrimSpace(fields[1]), `" `)
}

// parseSwaymsgTree does a best-effort extraction of the focused window from swaymsg output.
// This is a simplified parser — a full implementation would use JSON decoding.
func parseSwaymsgTree(output string) (string, string) {
	// Look for "focused": true and extract nearby "app_id" or "class"
	lines := strings.Split(output, "\n")
	for i, line := range lines {
		if strings.Contains(line, `"focused": true`) {
			// Search nearby lines for app_id
			for j := max(0, i-10); j < min(len(lines), i+10); j++ {
				if strings.Contains(lines[j], `"app_id"`) {
					parts := strings.SplitN(lines[j], ":", 2)
					if len(parts) == 2 {
						appID := strings.Trim(strings.TrimSpace(parts[1]), `",`)
						if appID != "null" && appID != "" {
							return appID, appID
						}
					}
				}
			}
		}
	}
	return "", ""
}

// parseLsappinfo extracts bundleID and name from lsappinfo output.
// Output format:
//
//	"bundleID"="com.apple.dt.Xcode"
//	"name"="Xcode"
func parseLsappinfo(output string) (bundleID, appName string) {
	for _, line := range strings.Split(output, "\n") {
		line = strings.TrimSpace(line)
		if k, v, ok := parseLsappinfoLine(line); ok {
			switch k {
			case "bundleID":
				bundleID = v
			case "name":
				appName = v
			}
		}
	}
	return bundleID, appName
}

// parseLsappinfoLine parses a single "key"="value" line.
func parseLsappinfoLine(line string) (key, value string, ok bool) {
	parts := strings.SplitN(line, "=", 2)
	if len(parts) != 2 {
		return "", "", false
	}
	key = strings.Trim(strings.TrimSpace(parts[0]), `"`)
	value = strings.Trim(strings.TrimSpace(parts[1]), `"`)
	return key, value, true
}
