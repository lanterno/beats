/**
 * ProjectStats — at-a-glance project shape rendered above the week-history
 * table. Pre-P4.0 the page led with sessions, which buried the project's
 * actual shape; this small lift gives users a one-glance read on how the
 * project tends to go.
 *
 * Cards: avg session · longest session · total session count · last tracked.
 */

import type { Session } from "@/entities/session";
import { formatDuration, parseUtcIso } from "@/shared/lib";

interface ProjectStatsProps {
	sessions: Session[];
	/** ISO timestamp of the most recent activity, surfaced as a relative
	 *  "X days ago" string. Comes through the P3.0 aggregation. */
	lastTrackedAt?: string;
}

function formatRelativeDays(iso: string | undefined): string {
	if (!iso) return "—";
	const ts = Date.parse(iso);
	if (Number.isNaN(ts)) return "—";
	const days = Math.floor((Date.now() - ts) / (24 * 60 * 60 * 1000));
	if (days <= 0) return "Today";
	if (days === 1) return "1 day ago";
	if (days < 30) return `${days} days ago`;
	const months = Math.floor(days / 30);
	if (months === 1) return "1 month ago";
	return `${months} months ago`;
}

export function ProjectStats({ sessions, lastTrackedAt }: ProjectStatsProps) {
	const completed = sessions.filter((s) => s.duration > 0);
	// No completed sessions yet — render a minimal placeholder so the page
	// still leads with a stats row (just one card) rather than collapsing.
	if (completed.length === 0) {
		return (
			<div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-2">
				<StatCard label="Last tracked" value={formatRelativeDays(lastTrackedAt)} />
			</div>
		);
	}

	const totalDuration = completed.reduce((sum, s) => sum + s.duration, 0);
	const avgMinutes = totalDuration / completed.length;
	const longestMinutes = Math.max(...completed.map((s) => s.duration));
	const sortedByStart = [...completed].sort(
		(a, b) => parseUtcIso(b.startTime).getTime() - parseUtcIso(a.startTime).getTime(),
	);
	const lastSession = sortedByStart[0];
	const lastTrackedFromSessions = lastSession
		? (lastSession.endTime ?? lastSession.startTime)
		: undefined;
	const effectiveLastTracked = lastTrackedAt ?? lastTrackedFromSessions;

	return (
		<div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-2">
			<StatCard label="Avg session" value={formatDuration(avgMinutes)} />
			<StatCard label="Longest" value={formatDuration(longestMinutes)} />
			<StatCard label="Sessions" value={`${completed.length}`} />
			<StatCard label="Last tracked" value={formatRelativeDays(effectiveLastTracked)} />
		</div>
	);
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
	return (
		<div className="rounded-md border border-border/60 bg-secondary/20 px-3 py-2 text-center">
			<p className="text-muted-foreground text-[10px] uppercase tracking-[0.12em] mb-0.5">
				{label}
			</p>
			<p className="text-sm font-medium tabular-nums text-foreground">{value}</p>
			{sub && <p className="text-[10px] text-muted-foreground">{sub}</p>}
		</div>
	);
}
