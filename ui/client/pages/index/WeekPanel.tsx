/**
 * WeekPanel Component
 * Navigable week section with two views:
 * - Daily view: per-project colored blocks per day
 * - Project totals view: horizontal bars showing weekly total per project
 */

import { CalendarDays, ChevronLeft, ChevronRight, List } from "lucide-react";
import { useState } from "react";
import { useProjects } from "@/entities/project";
import type { DayProjectBreakdown } from "@/entities/session";
import { useWeeklySessionsByProject } from "@/entities/session";
import { cn, formatDateShort, formatDuration, getWeekRange, startOfDay } from "@/shared/lib";
import { EmptyState, Panel } from "@/shared/ui";

/** The ‹ › round buttons, as on the project page. */
const NAV_BUTTON =
	"grid place-items-center w-7 h-7 rounded-full bg-secondary text-foreground hover:bg-sidebar-accent transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40 disabled:pointer-events-none";
/** The mockup's `.seg`: a pill group on the wash, the pressed option the accent (Settings, Insights). */
const SEG_BUTTON =
	"grid place-items-center w-7 h-7 rounded-full transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";
const SEG_ON = "bg-accent text-accent-foreground";
const SEG_OFF = "text-muted-foreground hover:text-foreground";

type ViewMode = "daily" | "projects";

export function WeekPanel() {
	const [weekOffset, setWeekOffset] = useState(0);
	const [view, setView] = useState<ViewMode>("daily");

	const { data: projects } = useProjects();
	const { data: weekData, isLoading } = useWeeklySessionsByProject(projects, weekOffset);

	const { start, end } = getWeekRange(weekOffset);
	const weekTotal = weekData?.reduce((sum, d) => sum + d.totalMinutes, 0) ?? 0;

	const weekLabel =
		weekOffset === 0
			? "This Week"
			: weekOffset === -1
				? "Last Week"
				: `${formatDateShort(start)} — ${formatDateShort(end)}`;

	return (
		<Panel padding="p-0" className="overflow-hidden">
			{/* Navigation row */}
			<div className="flex flex-wrap items-center gap-2 px-5 pt-4 pb-2">
				<button
					type="button"
					onClick={() => setWeekOffset((w) => w - 1)}
					className={NAV_BUTTON}
					aria-label="Previous week"
				>
					<ChevronLeft className="w-3.5 h-3.5" />
				</button>

				<div className="text-center min-w-[140px]">
					<span className="text-[13.5px] font-bold text-foreground">{weekLabel}</span>
					{weekOffset !== 0 && (
						<span className="text-xs font-medium text-muted-foreground ml-1.5 hidden sm:inline">
							{formatDateShort(start)} — {formatDateShort(end)}
						</span>
					)}
					{weekOffset === 0 && (
						<span className="text-xs font-medium text-muted-foreground ml-1.5 hidden sm:inline">
							{formatDateShort(start)} — {formatDateShort(end)}
						</span>
					)}
				</div>

				<button
					type="button"
					onClick={() => setWeekOffset((w) => Math.min(w + 1, 0))}
					disabled={weekOffset >= 0}
					className={NAV_BUTTON}
					aria-label="Next week"
				>
					<ChevronRight className="w-3.5 h-3.5" />
				</button>

				{weekOffset !== 0 && (
					<button
						type="button"
						onClick={() => setWeekOffset(0)}
						className="px-1.5 text-accent-ink text-[12.5px] font-bold hover:underline underline-offset-[3px] rounded-full focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
					>
						Today
					</button>
				)}

				<div className="ml-auto flex items-center gap-2">
					{weekTotal > 0 && (
						<span className="text-sm font-mono font-extrabold text-foreground">
							{formatDuration(weekTotal)}
						</span>
					)}

					<div className="flex gap-0.5 p-[3px] rounded-full bg-secondary">
						<button
							type="button"
							onClick={() => setView("daily")}
							className={cn(SEG_BUTTON, view === "daily" ? SEG_ON : SEG_OFF)}
							aria-pressed={view === "daily"}
							aria-label="Daily breakdown"
							title="Daily breakdown"
						>
							<CalendarDays className="w-3.5 h-3.5" />
						</button>
						<button
							type="button"
							onClick={() => setView("projects")}
							className={cn(SEG_BUTTON, view === "projects" ? SEG_ON : SEG_OFF)}
							aria-pressed={view === "projects"}
							aria-label="Project totals"
							title="Project totals"
						>
							<List className="w-3.5 h-3.5" />
						</button>
					</div>
				</div>
			</div>

			{/* Content */}
			{isLoading ? (
				<div className="h-32 flex items-center justify-center text-muted-foreground text-xs font-medium">
					Loading...
				</div>
			) : weekData && view === "daily" ? (
				<DailyView data={weekData} />
			) : weekData && view === "projects" ? (
				<ProjectTotalsView data={weekData} />
			) : (
				<EmptyState variant="chart" message="No data for this week yet" />
			)}
		</Panel>
	);
}

function DailyView({ data }: { data: DayProjectBreakdown[] }) {
	const today = startOfDay();

	return (
		// Seven columns from `sm`. Below it a column is ~38 px and every name read
		// "L…", so each day is a row there, its projects wrapping beside it.
		<div className="grid grid-cols-1 gap-1 px-3 pb-3 sm:grid-cols-7">
			{data.map((day) => {
				const isToday = day.date.getTime() === today.getTime();

				return (
					<div
						key={day.dayName}
						className={cn(
							"rounded-2xl min-w-0 flex items-center gap-2.5 px-2.5 py-1.5 sm:flex-col sm:items-stretch sm:gap-0 sm:px-1.5 sm:py-2 sm:min-h-[160px]",
							isToday && "bg-accent/20",
						)}
					>
						{/* Day header */}
						<div className="w-11 shrink-0 sm:w-auto sm:text-center sm:mb-2">
							<p
								className={cn(
									"text-xs font-bold uppercase tracking-wide leading-none",
									isToday ? "text-accent-ink" : "text-muted-foreground",
								)}
							>
								{day.dayName}
							</p>
							<p
								className={cn(
									"text-[10px] font-mono font-bold mt-1 leading-none",
									isToday ? "text-accent-ink" : "text-muted-foreground",
								)}
							>
								{formatDateShort(day.date)}
							</p>
						</div>

						{/* Project segments */}
						{day.segments.length > 0 ? (
							<>
								<div className="flex-1 min-w-0 flex flex-wrap gap-1 sm:flex-col sm:flex-nowrap">
									{day.segments.map((seg) => (
										// A wash in the project's own colour with its dot, not a
										// bordered box.
										<div
											key={seg.projectId}
											className="min-w-0 max-w-full flex items-center gap-1.5 rounded-xl px-2 py-1 leading-tight sm:block sm:px-1.5"
											style={{
												backgroundColor: `color-mix(in srgb, ${seg.projectColor} 18%, transparent)`,
											}}
										>
											<p className="flex items-center gap-1 text-xs font-bold text-foreground min-w-0">
												<span
													className="w-1.5 h-1.5 rounded-full shrink-0"
													style={{ backgroundColor: seg.projectColor }}
													aria-hidden="true"
												/>
												<span className="truncate">{seg.projectName}</span>
											</p>
											{/* Ink, not the muted tone: on the wash, and today's accent at dusk, muted fell to 3:1. */}
											<p className="text-[11px] font-mono font-bold text-foreground/85 whitespace-nowrap">
												{seg.minutes >= 60
													? `${(seg.minutes / 60).toFixed(1)}h`
													: `${Math.round(seg.minutes)}m`}
											</p>
										</div>
									))}
								</div>
								{/* Day total: the row's end below `sm`, the column's foot above */}
								<p
									className={cn(
										"shrink-0 text-center text-xs font-mono font-bold whitespace-nowrap sm:mt-auto sm:pt-1",
										isToday ? "text-accent-ink" : "text-muted-foreground",
									)}
								>
									{(day.totalMinutes / 60).toFixed(1)}h
								</p>
							</>
						) : (
							<div className="flex-1 flex items-center sm:justify-center">
								<span className="text-muted-foreground text-xs">—</span>
							</div>
						)}
					</div>
				);
			})}
		</div>
	);
}

function ProjectTotalsView({ data }: { data: DayProjectBreakdown[] }) {
	// Aggregate per project across all days
	const projectTotals = new Map<string, { name: string; color: string; minutes: number }>();
	for (const day of data) {
		for (const seg of day.segments) {
			const existing = projectTotals.get(seg.projectId);
			if (existing) {
				existing.minutes += seg.minutes;
			} else {
				projectTotals.set(seg.projectId, {
					name: seg.projectName,
					color: seg.projectColor,
					minutes: seg.minutes,
				});
			}
		}
	}

	const sorted = Array.from(projectTotals.values()).sort((a, b) => b.minutes - a.minutes);
	const maxMinutes = sorted.length > 0 ? sorted[0].minutes : 1;
	const weekTotal = sorted.reduce((sum, p) => sum + p.minutes, 0);

	if (sorted.length === 0) {
		return (
			<div className="h-32 flex items-center justify-center text-muted-foreground text-xs font-medium">
				No activity this week
			</div>
		);
	}

	return (
		<div className="px-5 pt-2 pb-4 space-y-1.5">
			{sorted.map((proj) => {
				const barWidth = (proj.minutes / maxMinutes) * 100;
				const hours = proj.minutes / 60;

				return (
					<div key={proj.name} className="flex items-center gap-2">
						<div
							className="w-2 h-2 rounded-full shrink-0"
							style={{ backgroundColor: proj.color }}
						/>
						<span className="text-xs font-bold text-foreground truncate min-w-0 w-24 shrink-0">
							{proj.name}
						</span>
						<div className="flex-1 h-2 rounded-full bg-muted">
							<div
								className="h-full rounded-full transition-all duration-300"
								style={{
									width: `${barWidth}%`,
									// A mix, not an appended alpha: the colour can be a var() fallback.
									backgroundColor: `color-mix(in srgb, ${proj.color} 70%, transparent)`,
								}}
							/>
						</div>
						<span className="text-xs font-mono font-bold text-foreground shrink-0 w-12 text-right">
							{hours >= 1 ? `${hours.toFixed(1)}h` : `${Math.round(proj.minutes)}m`}
						</span>
					</div>
				);
			})}

			{/* Week total footer */}
			<div className="flex items-center justify-end pt-2 border-t border-border">
				<span className="font-body text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground mr-2">
					Total
				</span>
				<span className="text-sm font-mono font-extrabold text-foreground">
					{formatDuration(weekTotal)}
				</span>
			</div>
		</div>
	);
}
