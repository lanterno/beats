/**
 * The health panel's words, apart from it so they can be tested. The API
 * answers figures, or the last figures and their age, or "unavailable"
 * (operator/health.py); every sentence here is the control plane's own, and
 * a figure Google had no points for reads as "no data", never as zero.
 */

import type { HealthReport } from "@/shared/api/schema";

export const MONITORING_CONSOLE =
	"https://console.cloud.google.com/monitoring/dashboards?project=beats-476914";

/** 0.9983 → "99.83%"; null → "no data". */
export function percent(value: number | null | undefined, digits = 2): string {
	if (value === null || value === undefined) return "no data";
	return `${(value * 100).toFixed(digits)}%`;
}

/** The headline: whether the product is meeting its target. */
export function healthHeadline(report: HealthReport): string {
	if (report.state === "unavailable" || !report.figures) {
		return "Live health is unavailable here.";
	}
	const a = report.figures.availability;
	if (a === null || a === undefined) return "No uptime data yet.";
	return a >= report.availability_target
		? `Up ${percent(a)} over the last day, above the ${percent(report.availability_target, 1)} target.`
		: `Up ${percent(a)} over the last day, below the ${percent(report.availability_target, 1)} target.`;
}

/** Said under the figures when they are not fresh. */
export function freshness(report: HealthReport): string | null {
	if (report.state !== "stale" || report.age_seconds === null || report.age_seconds === undefined) {
		return null;
	}
	const minutes = Math.max(1, Math.round(report.age_seconds / 60));
	return `Google did not answer. These figures are ${minutes} min old.`;
}

/** "1 of 2", "1", or "no data". */
export function instancesOf(report: HealthReport): string {
	const now = report.figures?.instances;
	if (now === null || now === undefined) return "no data";
	const max = report.max_instances;
	return max ? `${Math.round(now)} of ${max}` : String(Math.round(now));
}
