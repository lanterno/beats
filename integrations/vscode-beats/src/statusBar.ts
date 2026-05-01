/**
 * Pure formatting helpers for the Beats status-bar item. Lives outside
 * extension.ts so it has no `vscode` import — testable with plain
 * `node --test`.
 *
 * Two states:
 *  - "ok": daemon responded to /health. Show a zap icon + "Beats" so
 *    the user can see at a glance their heartbeats are landing.
 *  - "offline": fetch failed or daemon returned non-200. Show a slash-
 *    circle icon so the user knows their data isn't being captured.
 *    Tooltip explains: "Beats daemon offline — run `beatsd run`".
 */

/** Subset of the daemon's HealthResponse we actually display. */
export interface HealthSummary {
	ok: boolean;
	version: string;
	uptimeSec: number;
	editorCount: number;
}

/** Subset of the API's FlowWindowSummaryResponse the status bar uses.
 * Fields not used here (top_repo, top_language, etc.) are documented
 * separately on the daemon's GET /summary; this shape is intentionally
 * narrow so a server change adding new fields doesn't ripple through. */
export interface FlowSummary {
	count: number;
	avg: number;
	peak: number;
}

export interface StatusBarText {
	/** VS Code status-bar text — supports `$(icon)` codicon syntax. */
	text: string;
	/** Hovered tooltip — multiline, gives the user actionable context. */
	tooltip: string;
}

export function formatStatusBar(
	health: HealthSummary | null,
	summary: FlowSummary | null = null,
): StatusBarText {
	if (!health || !health.ok) {
		return {
			text: "$(circle-slash) Beats",
			tooltip:
				"Beats daemon offline — run `beatsd run` to start capturing flow data.\n\nClick to open the web Insights page anyway.",
		};
	}
	const v = health.version || "dev";
	const editorWord = health.editorCount === 1 ? "editor" : "editors";

	// When today's slice has at least one window, lead the status-bar
	// text with the avg score so the user sees a live number rather
	// than a binary connected/offline indicator. Falls back to plain
	// "Beats" early in the morning before any flow data has accrued.
	let text = "$(zap) Beats";
	const tooltipLines = [
		`Beats daemon connected (${v})`,
		`${health.editorCount} ${editorWord} sending heartbeats · uptime ${formatUptime(health.uptimeSec)}`,
	];
	if (summary && summary.count > 0) {
		const avg = Math.round(summary.avg * 100);
		const peak = Math.round(summary.peak * 100);
		text = `$(zap) Beats ${avg}`;
		tooltipLines.push(
			`Today: avg ${avg}/100 · peak ${peak}/100 · ${summary.count} windows`,
		);
	}
	tooltipLines.push("\nClick to open Insights.");
	return { text, tooltip: tooltipLines.join("\n") };
}

/**
 * Compact uptime display: "42s" / "12m" / "3h" / "2d 4h" depending on
 * magnitude. Tooltip-only, so we keep it short rather than precise.
 */
export function formatUptime(seconds: number): string {
	if (seconds < 0) return "0s";
	if (seconds < 60) return `${Math.floor(seconds)}s`;
	if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
	if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
	const days = Math.floor(seconds / 86400);
	const hours = Math.floor((seconds % 86400) / 3600);
	return hours > 0 ? `${days}d ${hours}h` : `${days}d`;
}
