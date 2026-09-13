/**
 * DistractionsToday — surfaces today's drift (distraction) events from the
 * daemon's shield. Shows total time spent drifting plus the top distracting
 * apps. Complements the Flow cards, which show focus QUALITY but never where
 * the day actually leaked. Hidden when there's no drift recorded today (so it
 * never shows an empty card for users not running the shield).
 */
import { useMemo } from "react";
import { useRecentDrift } from "@/entities/session";
import { formatDuration, shortBundleLabel } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { LABEL, META } from "./styles";

function startOfTodayIso(): string {
	const now = new Date();
	return new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
}

export function DistractionsToday() {
	const since = useMemo(startOfTodayIso, []);
	const { data: events, isLoading } = useRecentDrift(since, 100);

	const summary = useMemo(() => {
		if (!events || events.length === 0) return null;
		const byApp = new Map<string, number>();
		let totalSeconds = 0;
		for (const e of events) {
			totalSeconds += e.duration_seconds;
			byApp.set(e.bundle_id, (byApp.get(e.bundle_id) ?? 0) + e.duration_seconds);
		}
		const apps = [...byApp.entries()]
			.map(([bundleId, seconds]) => ({ bundleId, minutes: seconds / 60 }))
			.sort((a, b) => b.minutes - a.minutes)
			.slice(0, 5);
		return { totalMinutes: totalSeconds / 60, count: events.length, apps };
	}, [events]);

	// Hide entirely when there's nothing to report — an empty "distractions"
	// card would read as noise (and can't tell "focused" from "shield off").
	if (isLoading || !summary) return null;

	const maxMinutes = Math.max(...summary.apps.map((a) => a.minutes), 1);

	return (
		<Panel padding="px-6 py-[22px]" className="space-y-3">
			<div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
				<p className={LABEL}>Distractions today</p>
				<div className={`flex items-baseline gap-3 ${META}`}>
					<span>
						<span className="text-foreground font-bold tabular-nums">
							{formatDuration(summary.totalMinutes)}
						</span>{" "}
						drifting
					</span>
					<span>
						<span className="text-foreground font-bold tabular-nums">{summary.count}</span> event
						{summary.count !== 1 ? "s" : ""}
					</span>
				</div>
			</div>

			<div className="space-y-1.5">
				{summary.apps.map((a) => (
					<div key={a.bundleId} className="flex items-center gap-2">
						<span
							className="text-xs font-medium text-foreground w-28 truncate shrink-0"
							title={a.bundleId}
						>
							{shortBundleLabel(a.bundleId)}
						</span>
						<div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
							<div
								className="h-full rounded-full bg-destructive/60"
								style={{ width: `${(a.minutes / maxMinutes) * 100}%` }}
							/>
						</div>
						<span className="text-[11px] font-medium tabular-nums text-muted-foreground w-12 text-right shrink-0">
							{formatDuration(a.minutes)}
						</span>
					</div>
				))}
			</div>
		</Panel>
	);
}
