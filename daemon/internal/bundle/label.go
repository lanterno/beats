// Package bundle maps macOS bundle ids to human-friendly app names.
//
// Cross-language parity: matches ui/client/shared/lib/bundleLabel.ts
// and companion/lib/services/bundle_label.dart. All three render
// "VS Code" for "com.microsoft.VSCode" so the user sees the same name
// in the web FlowHeadline pill, the companion FlowScreen line, and
// the daemon CLI's `beatsd stats` output.
package bundle

import "strings"

var appLabels = map[string]string{
	"com.microsoft.VSCode":      "VS Code",
	"com.apple.dt.Xcode":        "Xcode",
	"com.jetbrains.intellij":    "IntelliJ",
	"com.jetbrains.WebStorm":    "WebStorm",
	"com.jetbrains.pycharm":     "PyCharm",
	"com.jetbrains.goland":      "GoLand",
	"com.googlecode.iterm2":     "iTerm",
	"com.apple.Terminal":        "Terminal",
	"com.mitchellh.ghostty":     "Ghostty",
	"net.kovidgoyal.kitty":      "Kitty",
	"com.tinyspeck.slackmacgap": "Slack",
	"com.hnc.Discord":           "Discord",
	"com.tdesktop.Telegram":     "Telegram",
	"com.google.Chrome":         "Chrome",
	"com.apple.Safari":          "Safari",
	"org.mozilla.firefox":       "Firefox",
	"com.brave.Browser":         "Brave",
	"com.figma.Desktop":         "Figma",
	"com.linear.linear":         "Linear",
	"notion.id":                 "Notion",
	"md.obsidian":               "Obsidian",
	"com.apple.mail":            "Mail",
	"com.spotify.client":        "Spotify",
	"com.apple.Music":           "Music",
	"com.apple.iCal":            "Calendar",
	"com.twitter.twitter-mac":   "Twitter",
}

// ShortLabel returns a human-friendly app name for a macOS bundle id,
// falling back to the trailing reverse-DNS segment for unknown ids.
// Empty input returns empty.
func ShortLabel(id string) string {
	if id == "" {
		return ""
	}
	if known, ok := appLabels[id]; ok {
		return known
	}
	// "com.foo.MyApp" → "MyApp". If there are no dots (rare), return
	// the input unchanged.
	if i := strings.LastIndex(id, "."); i >= 0 {
		return id[i+1:]
	}
	return id
}
