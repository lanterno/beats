/**
 * FlowByWeekday — sibling to FlowRhythm but on day-of-week, asking
 * "do I flow better on certain weekdays?" Pulls 28 days so each
 * weekday slot has at least ~4 samples to be meaningful (a 7-day
 * fetch would put a single Monday next to a single Friday and give
 * misleading-looking peaks).
 *
 * Renders 7 bars (Mon → Sun, ISO ordering — different from JS's
 * Sunday-first getDay() because work weeks read better Mon-first).
 * Empty weekdays render as a thin placeholder so the chart width is
 * constant and the user can see "you barely worked Sundays" as a
 * gap rather than a missing bar.
 */
import { useMemo } from "react";
import { useFlowWindowsLastDays } from "@/entities/session";
import { aggregateFlowByWeekday } from "@/shared/lib/flowAggregation";

const DAYS = 28;
const MIN_WINDOWS_TO_RENDER = 50; // ~50 minutes across 4 weeks — below that, weekday means are noise
// JS getDay() ordering: Sun=0..Sat=6. We display Mon-first; this lookup
// translates display index → getDay() index.
const DISPLAY_ORDER = [1, 2, 3, 4, 5, 6, 0];
const LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function FlowByWeekday({
	projectId,
	editorRepo,
	editorLanguage,
	bundleId,
}: {
	projectId?: string;
	editorRepo?: string;
	editorLanguage?: string;
	bundleId?: string;
} = {}) {
	const filter =
		projectId || editorRepo || editorLanguage || bundleId
			? { projectId, editorRepo, editorLanguage, bundleId }
			: undefined;
	const { data: windows, isLoading } = useFlowWindowsLastDays(DAYS, filter);

	const stats = useMemo(() => aggregateFlowByWeekday(windows ?? []), [windows]);
	const totalWindows = useMemo(() => stats.reduce((s, d) => s + d.count, 0), [stats]);

	if (isLoading) return null;
	if (totalWindows < MIN_WINDOWS_TO_RENDER) return null;

	const byWeekday = new Map(stats.map((s) => [s.weekday, s]));
	// Peak across populated days; tiebreak on earliest display index so
	// "Monday and Friday tied" reads as the earlier one.
	let peakIdx = 0;
	let peakAvg = -Infinity;
	for (let i = 0; i < DISPLAY_ORDER.length; i++) {
		const cell = byWeekday.get(DISPLAY_ORDER[i]);
		if (cell && cell.avg > peakAvg) {
			peakAvg = cell.avg;
			peakIdx = i;
		}
	}
	const peakLabel = LABELS[peakIdx];
	const peakCount = byWeekday.get(DISPLAY_ORDER[peakIdx])?.count ?? 0;

	return (
		<div className="rounded-lg border border-border/60 bg-secondary/20 px-4 py-3 space-y-3">
			<div className="flex items-baseline justify-between">
				<p className="font-heading text-sm text-foreground">Flow by weekday</p>
				<p className="text-[11px] text-muted-foreground">last {DAYS} days · ISO week</p>
			</div>

			<div
				className="flex items-end gap-2 h-20"
				role="group"
				aria-label="Average flow score per day of the week"
			>
				{DISPLAY_ORDER.map((dayIdx, displayIdx) => {
					const cell = byWeekday.get(dayIdx);
					const isPeak = displayIdx === peakIdx;
					return (
						<div key={dayIdx} className="flex-1 flex flex-col items-center gap-1.5">
							<div className="relative w-full flex-1 flex items-end">
								<div
									className={`w-full rounded-sm transition-all ${
										!cell ? "bg-secondary/40" : isPeak ? "bg-accent" : "bg-accent/55"
									}`}
									style={{
										height: cell ? `${Math.max(4, cell.avg * 100)}%` : "0%",
									}}
									title={
										cell
											? `${LABELS[displayIdx]}: ${Math.round(cell.avg * 100)}/100 across ${cell.count} windows`
											: `${LABELS[displayIdx]}: no data`
									}
								/>
							</div>
							<div
								className={`text-[10px] tabular-nums ${
									isPeak ? "text-accent font-medium" : "text-muted-foreground"
								}`}
							>
								{LABELS[displayIdx]}
							</div>
						</div>
					);
				})}
			</div>

			{peakCount > 0 && (
				<p className="text-[10px] text-muted-foreground border-t border-border/40 pt-2">
					Best weekday over the last {DAYS} days:{" "}
					<span className="text-foreground">{peakLabel}</span> at {Math.round(peakAvg * 100)}/100.
				</p>
			)}
		</div>
	);
}
