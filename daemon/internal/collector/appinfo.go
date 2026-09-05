package collector

import (
	"os/exec"
	"runtime"
	"strings"
)

// FrontmostApp returns the bundle ID and name of the frontmost application.
// On macOS, uses lsappinfo. On Linux, uses xdotool + xprop (X11) or
// swaymsg (Wayland). On Windows, uses GetForegroundWindow +
// QueryFullProcessImageName. Returns empty strings on any error
// (graceful degradation).
func FrontmostApp() (bundleID, appName string) {
	switch runtime.GOOS {
	case "darwin":
		return frontmostAppMacOS()
	case "linux":
		return frontmostAppLinux()
	case "windows":
		return frontmostAppWindows()
	default:
		return "", ""
	}
}

// windowsExeIdentity derives the app identity from a full Windows
// executable path — "C:\Program Files\Microsoft VS Code\Code.exe" →
// ("Code", "Code").
//
// Both halves are the extension-less basename, deliberately. The
// obvious richer source for appName is the window title, and we do not
// use it: titles routinely carry the open document's name and full
// path ("budget-2026.xlsx — Excel"), which would violate the daemon's
// "no file paths beyond the workspace root" guarantee. The exe name is
// the stable identity anyway — it's what survives a window title
// changing every time the user switches tabs.
//
// The extension is stripped so the value survives bundle.ShortLabel,
// which splits unknown ids on the final dot: "Code.exe" would render
// as "exe" in the web pill, the companion's flow line, and `beatsd
// stats` alike.
//
// Lives here rather than in appinfo_windows.go so it's testable on any
// platform; it takes a path string and touches no syscalls.
func windowsExeIdentity(fullPath string) (bundleID, appName string) {
	if fullPath == "" {
		return "", ""
	}

	// Split on either separator. filepath.Base is not usable here: on a
	// non-Windows host it doesn't treat "\" as a separator, which would
	// break both the tests and any cross-platform reuse.
	base := fullPath
	if i := strings.LastIndexAny(base, `\/`); i >= 0 {
		base = base[i+1:]
	}

	// Strip a trailing ".exe" case-insensitively. Anything else (".com",
	// ".scr") is left alone — it's rare enough that keeping the literal
	// name is the more honest answer than guessing at extensions.
	if len(base) > 4 && strings.EqualFold(base[len(base)-4:], ".exe") {
		base = base[:len(base)-4]
	}

	if base == "" {
		return "", ""
	}
	return base, base
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
//
// Strategy: find the line carrying `"focused": true`, then scan UPWARD
// (toward the parent JSON object) for the nearest `"app_id"` field.
// In every swaymsg pretty-print I've seen, app_id sits above focused
// inside the same node block — so the closest preceding occurrence is
// always the right one. Scanning downward (an earlier version of this
// code did) would let an unrelated sibling's app_id leak through when
// multiple windows live in the tree.
func parseSwaymsgTree(output string) (string, string) {
	lines := strings.Split(output, "\n")
	for i, line := range lines {
		if strings.Contains(line, `"focused": true`) {
			// Scan upward from the focused line, closest first. The
			// 10-line cap covers typical sway tree indentation
			// (siblings are 2-4 fields apart) without crossing into
			// the next node block.
			for j := i - 1; j >= max(0, i-10); j-- {
				if !strings.Contains(lines[j], `"app_id"`) {
					continue
				}
				parts := strings.SplitN(lines[j], ":", 2)
				if len(parts) != 2 {
					continue
				}
				appID := strings.Trim(strings.TrimSpace(parts[1]), `",`)
				if appID != "null" && appID != "" {
					return appID, appID
				}
				// app_id present but null — XWayland windows. Stop;
				// the daemon's frontmostAppLinux will fall through
				// to the X11 path.
				return "", ""
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
