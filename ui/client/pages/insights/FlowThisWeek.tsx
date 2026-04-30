/**
 * FlowThisWeek — last 7 calendar days of flow scores as a bar chart.
 *
 * Backfills empty days so the chart width is constant — a missed day
 * reads as a clear gap rather than the bars sliding around. The user's
 * peak day across the window is annotated below.
 */
import { useMemo } from "react";
import { useFlowWindowsLastDays } from "@/entities/session";
import { aggregateFlowByDay } from "@/shared/lib/flowAggregation";

const DAYS = 7;
const DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

interface DayBucket {
	date: string;
	avg: number;
	count: number;
	label: string;
	isToday: boolean;
}

export function FlowThisWeek({ projectId }: { projectId?: string } = {}) {
	const filter = projectId ? { projectId } : undefined;
	const { data: windows, isLoading } = useFlowWindowsLastDays(DAYS, filter);

	const buckets = useMemo<DayBucket[]>(() => {
		if (!windows) return [];

		// Index aggregations by local YYYY-MM-DD so we can backfill.
		const byDay = new Map(aggregateFlowByDay(windows).map((d) => [d.date, d]));

		const today = new Date();
		const todayStr = dateKey(today);
		const out: DayBucket[] = [];
		for (let i = DAYS - 1; i >= 0; i--) {
			const d = new Date(today);
			d.setDate(today.getDate() - i);
			const key = dateKey(d);
			const found = byDay.get(key);
			out.push({
				date: key,
				avg: found?.avg ?? 0,
				count: found?.count ?? 0,
				label: DAY_LABELS[d.getDay()],
				isToday: key === todayStr,
			});
		}
		return out;
	}, [windows]);

	if (isLoading) return null;
	const totalWindows = buckets.reduce((s, b) => s + b.count, 0);
	if (totalWindows === 0) return null;

	const peakIdx = buckets.reduce((best, cur, i, arr) => (cur.avg > arr[best].avg ? i : best), 0);
	const peak = buckets[peakIdx];

	return (
		<div className="rounded-lg border border-border/60 bg-secondary/20 px-4 py-3 space-y-3">
			<div className="flex items-baseline justify-between">
				<p className="font-heading text-sm text-foreground">Flow this week</p>
				<p className="text-[11px] text-muted-foreground">last {DAYS} days</p>
			</div>

			<div className="flex items-end gap-2 h-24" role="group" aria-label="Daily flow score">
				{buckets.map((b) => (
					<div key={b.date} className="flex-1 flex flex-col items-center gap-1.5">
						<div className="relative w-full flex-1 flex items-end">
							<div
								className={`w-full rounded-sm transition-all ${b.count === 0 ? "bg-secondary/40" : b.isToday ? "bg-accent" : "bg-accent/60"}`}
								style={{
									// Pin a 4px floor so days with very low scores still
									// have a visible mark, distinguishable from the no-data
									// bar (which uses the muted secondary color).
									height: `${Math.max(b.count === 0 ? 0 : 4, b.avg * 100)}%`,
								}}
								title={
									b.count === 0
										? `${b.date}: no data`
										: `${b.date}: ${Math.round(b.avg * 100)}/100 across ${b.count} windows`
								}
							/>
						</div>
						<div
							className={`text-[10px] tabular-nums ${b.isToday ? "text-accent font-medium" : "text-muted-foreground"}`}
						>
							{b.label}
						</div>
					</div>
				))}
			</div>

			{peak.count > 0 && (
				<p className="text-[10px] text-muted-foreground border-t border-border/40 pt-2">
					Best day this week: <span className="text-foreground">{formatDate(peak.date)}</span> at{" "}
					{Math.round(peak.avg * 100)}/100.
				</p>
			)}
		</div>
	);
}

function dateKey(d: Date): string {
	const y = d.getFullYear();
	const m = String(d.getMonth() + 1).padStart(2, "0");
	const day = String(d.getDate()).padStart(2, "0");
	return `${y}-${m}-${day}`;
}

function formatDate(yyyymmdd: string): string {
	const [y, m, d] = yyyymmdd.split("-").map(Number);
	const date = new Date(y, m - 1, d);
	return date.toLocaleDateString(undefined, { weekday: "long" });
}
