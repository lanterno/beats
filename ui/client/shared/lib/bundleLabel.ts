/**
 * Best-effort mapping from common macOS bundle ids → human labels,
 * plus a `shortBundleLabel` helper that falls back to the trailing
 * reverse-DNS segment for ids we don't recognize.
 *
 * Lives in shared/lib so both the Insights FlowByApp card and the
 * home FlowHeadline can render the same friendly name. Unknown ids
 * fall through to "MyApp" from "com.foo.MyApp" — at least
 * recognizable to anyone who's seen `osascript` output.
 */

const APP_LABELS: Record<string, string> = {
	"com.microsoft.VSCode": "VS Code",
	"com.apple.dt.Xcode": "Xcode",
	"com.jetbrains.intellij": "IntelliJ",
	"com.jetbrains.WebStorm": "WebStorm",
	"com.jetbrains.pycharm": "PyCharm",
	"com.jetbrains.goland": "GoLand",
	"com.googlecode.iterm2": "iTerm",
	"com.apple.Terminal": "Terminal",
	"com.mitchellh.ghostty": "Ghostty",
	"net.kovidgoyal.kitty": "Kitty",
	"com.tinyspeck.slackmacgap": "Slack",
	"com.hnc.Discord": "Discord",
	"com.tdesktop.Telegram": "Telegram",
	"com.google.Chrome": "Chrome",
	"com.apple.Safari": "Safari",
	"org.mozilla.firefox": "Firefox",
	"com.brave.Browser": "Brave",
	"com.figma.Desktop": "Figma",
	"com.linear.linear": "Linear",
	"notion.id": "Notion",
	"md.obsidian": "Obsidian",
	"com.apple.mail": "Mail",
	"com.spotify.client": "Spotify",
	"com.apple.Music": "Music",
	"com.apple.iCal": "Calendar",
	"com.twitter.twitter-mac": "Twitter",
};

/**
 * Returns a human-friendly app name for a macOS bundle id, falling
 * back to the trailing reverse-DNS segment for unknown ids. Empty
 * input returns empty.
 */
export function shortBundleLabel(id: string): string {
	if (!id) return "";
	const known = APP_LABELS[id];
	if (known) return known;
	const dot = id.lastIndexOf(".");
	return dot >= 0 ? id.slice(dot + 1) : id;
}
