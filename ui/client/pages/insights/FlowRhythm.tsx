/**
 * FlowRhythm — bins the last 7 days of flow windows by hour-of-day and
 * shows when in the day the user tends to flow best. Different question
 * than FlowThisWeek (which day) and FlowToday (today's shape) — answers
 * "when in my day should I protect time for deep work?"
 *
 * Renders a 24-bar chart, one per hour of local time. Bars for hours
 * with no data render as a thin track so the chart stays a constant
 * width and the user can see the "shape of the day" instantly. The peak
 * hour is annotated below.
 */
import { useMemo } from "react";
import { useFlowWindowsLastDays } from "@/entities/session";
import { aggregateFlowByHour } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { FOOTNOTE, LABEL, META } from "./styles";

const DAYS = 7;
const MIN_WINDOWS_TO_RENDER = 12; // about 12 minutes of data — below that, bars are noise

export function FlowRhythm({
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

	const stats = useMemo(() => aggregateFlowByHour(windows ?? []), [windows]);
	const totalWindows = useMemo(() => stats.reduce((s, h) => s + h.count, 0), [stats]);

	if (isLoading) return null;
	if (totalWindows < MIN_WINDOWS_TO_RENDER) return null;

	// Peak: highest avg across populated hours. Tie-break on earliest hour
	// so "morning person" and "evening person" both get a stable answer.
	const peak = stats.reduce((best, cur) => (cur.avg > best.avg ? cur : best), stats[0]);

	// Build a 24-slot lookup so the chart is fixed-width regardless of
	// gaps. The aggregator returns only populated hours; we fill the rest.
	const byHour = new Map(stats.map((h) => [h.hour, h]));

	return (
		<Panel padding="px-6 py-[22px]" className="space-y-3">
			<div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
				<p className={LABEL}>Flow rhythm</p>
				<p className={META}>last {DAYS} days · by hour of day</p>
			</div>

			{/* biome-ignore lint/a11y/useSemanticElements: <fieldset> is the rule's suggestion, but these group chart bars and filter chips rather than form controls, and fieldset's UA min-inline-size breaks the flex row. role="group" with an accessible name is the correct ARIA here. */}
			<div
				className="flex items-end gap-[2px] h-20"
				role="group"
				aria-label="Average flow score per hour of day"
			>
				{Array.from({ length: 24 }, (_, h) => {
					const cell = byHour.get(h);
					const isPeak = peak && cell && cell.hour === peak.hour;
					return (
						<div key={h} className="flex-1 self-stretch flex flex-col items-center gap-1">
							<div className="relative w-full flex-1 flex items-end">
								<div
									className={`w-full rounded-t-[4px] rounded-b-[2px] transition-all ${
										!cell ? "bg-muted" : isPeak ? "bg-success" : "bg-success/45"
									}`}
									style={{
										height: cell ? `${Math.max(4, cell.avg * 100)}%` : "0%",
									}}
									title={
										cell
											? `${formatHour(h)}: ${Math.round(cell.avg * 100)}/100 across ${cell.count} windows`
											: `${formatHour(h)}: no data`
									}
								/>
							</div>
						</div>
					);
				})}
			</div>

			{/* Sparse hour labels — every 6 hours keeps the row readable. */}
			<div className="flex text-[9.5px] font-bold font-mono tabular-nums text-muted-foreground">
				{[0, 6, 12, 18].map((h, i) => (
					<div
						key={h}
						className="flex-1 text-left"
						style={{ marginLeft: i === 0 ? "0" : undefined }}
					>
						{formatHour(h)}
					</div>
				))}
			</div>

			{peak && peak.count > 0 && (
				<p className={FOOTNOTE}>
					You flow best around{" "}
					<span className="text-foreground font-bold">{formatHour(peak.hour)}</span> — averaging{" "}
					{Math.round(peak.avg * 100)}/100 across {peak.count} windows.
				</p>
			)}
		</Panel>
	);
}

function formatHour(h: number): string {
	return `${String(h).padStart(2, "0")}:00`;
}
