package collector

// bundleCategories maps macOS bundle IDs to activity categories.
// Used for category_fit_score in the Flow Score algorithm.
var bundleCategories = map[string]string{
	// Coding
	"com.apple.dt.Xcode":            "coding",
	"com.microsoft.VSCode":          "coding",
	"com.apple.Terminal":            "coding",
	"com.googlecode.iterm2":         "coding",
	"co.zeit.hyper":                 "coding",
	"com.github.wez.wezterm":        "coding",
	"dev.warp.Warp-Stable":          "coding",
	"com.todesktop.230313mzl4w4u92": "coding", // Cursor
	"com.jetbrains.intellij":        "coding",
	"com.jetbrains.intellij.ce":     "coding",
	"com.jetbrains.goland":          "coding",
	"com.jetbrains.pycharm":         "coding",
	"com.jetbrains.pycharm.ce":      "coding",
	"com.jetbrains.WebStorm":        "coding",
	"com.jetbrains.rider":           "coding",
	"com.jetbrains.CLion":           "coding",
	"com.jetbrains.rustrover":       "coding",
	"com.sublimetext.4":             "coding",
	"com.sublimetext.3":             "coding",
	"com.panic.Nova":                "coding",
	"com.docker.docker":             "coding",

	// Communication
	"com.tinyspeck.slackmacgap":    "communication",
	"com.microsoft.teams2":         "communication",
	"com.hnc.Discord":              "communication",
	"com.apple.MobileSMS":          "communication",
	"com.apple.mail":               "communication",
	"com.readdle.smartemail-macos": "communication",
	"us.zoom.xos":                  "communication",
	"com.microsoft.Outlook":        "communication",

	// Browser
	"com.apple.Safari":           "browser",
	"com.google.Chrome":          "browser",
	"org.mozilla.firefox":        "browser",
	"company.thebrowser.Browser": "browser", // Arc
	"com.brave.Browser":          "browser",
	"com.vivaldi.Vivaldi":        "browser",
	"com.operasoftware.Opera":    "browser",
	"org.chromium.Chromium":      "browser",

	// Design
	"com.figma.Desktop":             "design",
	"com.bohemiancoding.sketch3":    "design",
	"com.serif.affinity-designer-2": "design",
	"com.serif.affinity-photo-2":    "design",
	"com.adobe.Photoshop":           "design",
	"com.adobe.illustrator":         "design",

	// Writing
	"notion.id":                    "writing",
	"md.obsidian":                  "writing",
	"com.apple.iWork.Pages":        "writing",
	"com.microsoft.Word":           "writing",
	"com.google.android.apps.docs": "writing",
	"net.ia.iaWriter":              "writing",
	"com.apple.Notes":              "writing",

	// Linux apps (WM_CLASS or Sway app_id)
	"code":               "coding", // VS Code on Linux
	"Code":               "coding",
	"Alacritty":          "coding",
	"kitty":              "coding",
	"foot":               "coding",
	"Emacs":              "coding",
	"Neovide":            "coding",
	"jetbrains-idea":     "coding",
	"jetbrains-goland":   "coding",
	"jetbrains-pycharm":  "coding",
	"Slack":              "communication",
	"discord":            "communication",
	"thunderbird":        "communication",
	"firefox":            "browser",
	"chromium":           "browser",
	"Google-chrome":      "browser",
	"Brave-browser":      "browser",
	"org.gnome.Nautilus": "other",

	// Social / media
	"com.twitter.twitter-mac": "social",
	"tv.twitch.studio":        "social",
	"com.spotify.client":      "social",
	"com.apple.Music":         "social",
	"com.netflix.Netflix":     "social",
}

// CategoryFor returns the activity category for a given macOS bundle ID.
// Returns "other" for unknown bundle IDs.
func CategoryFor(bundleID string) string {
	if cat, ok := bundleCategories[bundleID]; ok {
		return cat
	}
	return "other"
}
