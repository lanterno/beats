package collector

import "strings"

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

	// Windows apps, keyed by the extension-less executable basename
	// that windowsExeIdentity emits ("Code.exe" → "Code"). Casing here
	// is the on-disk casing QueryFullProcessImageName returns, but
	// CategoryFor also falls back to a case-insensitive match, so an
	// installer that ships a differently-cased name still resolves.
	//
	// Coding
	"Code - Insiders": "coding",
	"Cursor":          "coding",
	"devenv":          "coding", // Visual Studio
	"idea64":          "coding",
	"goland64":        "coding",
	"pycharm64":       "coding",
	"webstorm64":      "coding",
	"rider64":         "coding",
	"clion64":         "coding",
	"rustrover64":     "coding",
	"studio64":        "coding", // Android Studio
	"sublime_text":    "coding",
	"notepad++":       "coding",
	"WindowsTerminal": "coding",
	"powershell":      "coding",
	"pwsh":            "coding",
	"cmd":             "coding",
	"wezterm-gui":     "coding",
	"mintty":          "coding", // Git Bash
	"nvim":            "coding",
	"gvim":            "coding",
	"Docker Desktop":  "coding",

	// Communication
	"slack":    "communication",
	"ms-teams": "communication",
	"Teams":    "communication",
	"Discord":  "communication",
	"OUTLOOK":  "communication",
	"olk":      "communication", // new Outlook
	"Zoom":     "communication",
	"Telegram": "communication",
	"WhatsApp": "communication",
	"Signal":   "communication",

	// Browser
	"chrome":  "browser",
	"msedge":  "browser",
	"brave":   "browser",
	"opera":   "browser",
	"vivaldi": "browser",
	"Arc":     "browser",

	// Design
	"Figma":            "design",
	"Photoshop":        "design",
	"Illustrator":      "design",
	"AffinityDesigner": "design",
	"AffinityPhoto":    "design",
	"blender":          "design",

	// Writing
	"Notion":   "writing",
	"Obsidian": "writing",
	"WINWORD":  "writing",
	"ONENOTE":  "writing",
	"Typora":   "writing",
	"notepad":  "writing",

	// Social / media
	"Spotify": "social",
	"Netflix": "social",
	"steam":   "social",
	"vlc":     "social",
}

// lowerBundleCategories indexes bundleCategories by lowercased key, for
// the case-insensitive fallback in CategoryFor.
//
// Built once at init rather than lowercasing the map on every lookup —
// CategoryFor runs on every sample, and the map is a compile-time
// constant in practice.
//
// Collisions are possible in principle (two keys differing only by
// case) but harmless here: every such pair in the map above maps to
// the same category, so whichever wins gives the same answer.
var lowerBundleCategories = func() map[string]string {
	m := make(map[string]string, len(bundleCategories))
	for k, v := range bundleCategories {
		m[strings.ToLower(k)] = v
	}
	return m
}()

// CategoryFor returns the activity category for a given app identity —
// a macOS bundle ID, a Linux WM_CLASS / Sway app_id, or a Windows
// executable basename.
//
// Falls back to a case-insensitive lookup before giving up, because
// the three platforms disagree about casing for the same app
// ("Code" on Windows, "code" on Linux) and a case miss is
// indistinguishable from an unknown app in the resulting score.
//
// Returns "other" for unknown identities.
func CategoryFor(bundleID string) string {
	if cat, ok := bundleCategories[bundleID]; ok {
		return cat
	}
	if cat, ok := lowerBundleCategories[strings.ToLower(bundleID)]; ok {
		return cat
	}
	return "other"
}
