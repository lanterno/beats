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
	/** How many flow windows this daemon process has POSTed since
	 * startup. A 0 here on a daemon that's been up for a while is a
	 * useful "is the collector actually producing?" signal — usually
	 * means Accessibility permission was revoked mid-session. */
	windowsEmitted: number;
}

/** Subset of the API's FlowWindowSummaryResponse the status bar uses.
 * Stays narrow so a server change adding new fields doesn't ripple
 * through; topRepo / topLanguage are surfaced in the tooltip when
 * present, omitted cleanly when null (no editor heartbeats covered
 * the slice). */
export interface FlowSummary {
	count: number;
	avg: number;
	peak: number;
	topRepo?: string;
	topLanguage?: string;
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
	// Build the daemon-info line with `· N emitted` appended when the
	// counter is non-zero. Daemons started more than a minute ago
	// with 0 emitted windows often mean Accessibility permission got
	// revoked — surfacing the count gives the user something concrete
	// to spot.
	const daemonLine =
		`${health.editorCount} ${editorWord} sending heartbeats · uptime ${formatUptime(health.uptimeSec)}` +
		(health.windowsEmitted > 0
			? ` · ${health.windowsEmitted} emitted`
			: "");
	const tooltipLines = [
		`Beats daemon connected (${v})`,
		daemonLine,
	];
	if (summary && summary.count > 0) {
		const avg = Math.round(summary.avg * 100);
		const peak = Math.round(summary.peak * 100);
		text = `$(zap) Beats ${avg}`;
		tooltipLines.push(
			`Today: avg ${avg}/100 · peak ${peak}/100 · ${summary.count} windows`,
		);
		// Best-axis line — same info the home FlowHeadline shows, in
		// the editor that's producing the heartbeats. Omitted cleanly
		// when no editor context covered the slice (the tooltip would
		// just say "best on : in" otherwise).
		const bestParts: string[] = [];
		if (summary.topRepo) bestParts.push(`best on ${shortRepoTail(summary.topRepo)}`);
		if (summary.topLanguage) bestParts.push(`in ${summary.topLanguage}`);
		if (bestParts.length > 0) {
			tooltipLines.push(bestParts.join(" · "));
		}
	}
	tooltipLines.push("\nClick to open Insights.");
	return { text, tooltip: tooltipLines.join("\n") };
}

/**
 * Last two path segments of a repo path. Cross-language parity with
 * the daemon's shortRepoTrail (Go) and the companion's shortRepoTail
 * (Dart) — same algorithm, kept consistent so users see the same
 * shortened display string everywhere.
 */
export function shortRepoTail(repo: string): string {
	const parts = repo.split(/[\\/]/).filter(Boolean);
	if (parts.length <= 2) return repo;
	return parts.slice(-2).join("/");
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
