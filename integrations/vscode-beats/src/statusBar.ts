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

export interface StatusBarText {
	/** VS Code status-bar text — supports `$(icon)` codicon syntax. */
	text: string;
	/** Hovered tooltip — multiline, gives the user actionable context. */
	tooltip: string;
}

export function formatStatusBar(health: HealthSummary | null): StatusBarText {
	if (!health || !health.ok) {
		return {
			text: "$(circle-slash) Beats",
			tooltip:
				"Beats daemon offline — run `beatsd run` to start capturing flow data.\n\nClick to open the web Insights page anyway.",
		};
	}
	const v = health.version || "dev";
	const editorWord = health.editorCount === 1 ? "editor" : "editors";
	return {
		text: "$(zap) Beats",
		tooltip: `Beats daemon connected (${v})\n${health.editorCount} ${editorWord} sending heartbeats · uptime ${formatUptime(health.uptimeSec)}\n\nClick to open Insights.`,
	};
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
