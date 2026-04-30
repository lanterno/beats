/**
 * FlowByApp — third axis of the per-window grouping cards. Sits next to
 * FlowByRepo and FlowByLanguage and uses the same aggregateFlowBy helper.
 * Renders the bundle id as a friendly app name when we recognize it.
 *
 * Why a card per dimension instead of a tabbed picker: each axis answers
 * a slightly different question and they're useful at-a-glance side by
 * side. A tab would force the user to flip and lose context.
 */
import { useMemo } from "react";
import { useFlowWindows } from "@/entities/session";
import { aggregateFlowBy } from "@/shared/lib/flowAggregation";

// Best-effort mapping from common bundle ids → human labels. Anything
// not listed falls through to the bundle id itself, which is at least
// recognizable to anyone who's seen `osascript` output.
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

function shortBundleLabel(id: string): string {
	const known = APP_LABELS[id];
	if (known) return known;
	// Fallback: the last segment of a reverse-DNS bundle id is usually the
	// most recognizable piece. "com.foo.MyApp" → "MyApp". If there are no
	// dots (rare), return as-is.
	const dot = id.lastIndexOf(".");
	return dot >= 0 ? id.slice(dot + 1) : id;
}

export function FlowByApp({ projectId }: { projectId?: string } = {}) {
	const filter = projectId ? { projectId } : undefined;
	const { data: windows } = useFlowWindows(undefined, undefined, filter);
	const stats = useMemo(
		() => aggregateFlowBy(windows ?? [], (w) => w.dominant_bundle_id, 5),
		[windows],
	);

	if (stats.length === 0) return null;
	const peakAvg = Math.max(...stats.map((s) => s.avg));

	return (
		<div className="rounded-lg border border-border/60 bg-secondary/20 px-4 py-3 space-y-3">
			<div className="flex items-baseline justify-between">
				<p className="font-heading text-sm text-foreground">Flow by app</p>
				<p className="text-[11px] text-muted-foreground">
					today · {stats.length} {stats.length === 1 ? "app" : "apps"}
				</p>
			</div>

			<div className="space-y-2">
				{stats.map((s) => (
					<div key={s.key} className="flex items-center gap-3">
						<div className="text-foreground/80 truncate text-xs flex-1 min-w-0" title={s.key}>
							{shortBundleLabel(s.key)}
						</div>
						<div className="flex-[2] h-1.5 rounded-full bg-secondary/60 relative overflow-hidden">
							<div
								className="absolute inset-y-0 left-0 bg-accent"
								style={{ width: `${(s.avg * 100).toFixed(1)}%` }}
							/>
						</div>
						<div className="text-[11px] tabular-nums text-foreground w-9 text-right">
							{Math.round(s.avg * 100)}
						</div>
						<div className="text-[10px] tabular-nums text-muted-foreground w-12 text-right">
							{s.minutes}m
						</div>
					</div>
				))}
			</div>

			{stats.length >= 2 && (
				<p className="text-[10px] text-muted-foreground border-t border-border/40 pt-2">
					Best flow today in{" "}
					<span className="text-foreground">
						{shortBundleLabel(stats.find((s) => s.avg === peakAvg)?.key ?? "")}
					</span>{" "}
					at {Math.round(peakAvg * 100)}/100.
				</p>
			)}
		</div>
	);
}
