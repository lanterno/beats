/**
 * ContributionHeatmap Component
 * GitHub-style 52-week grid showing daily activity intensity.
 */

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { useHeatmap } from "@/entities/session";
import type { HeatmapDay } from "@/shared/api";
import { cn } from "@/shared/lib";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/shared/ui";

const DAY_LABELS = ["Mon", "", "Wed", "", "Fri", "", ""];
const MONTH_NAMES = [
	"Jan",
	"Feb",
	"Mar",
	"Apr",
	"May",
	"Jun",
	"Jul",
	"Aug",
	"Sep",
	"Oct",
	"Nov",
	"Dec",
];

function getIntensity(minutes: number): number {
	if (minutes === 0) return 0;
	if (minutes < 60) return 1;
	if (minutes < 180) return 2;
	if (minutes < 360) return 3;
	return 4;
}

const INTENSITY_CLASSES = [
	"bg-muted/30",
	"bg-accent/20",
	"bg-accent/40",
	"bg-accent/65",
	"bg-accent",
];

function buildGrid(year: number, data: HeatmapDay[]) {
	const dataMap = new Map(data.map((d) => [d.date, d]));

	// Find the first Monday on or before Jan 1
	const jan1 = new Date(year, 0, 1);
	const startDay = jan1.getDay(); // 0=Sun
	const mondayOffset = startDay === 0 ? -6 : 1 - startDay;
	const gridStart = new Date(year, 0, 1 + mondayOffset);

	// Build 53 weeks × 7 days
	const weeks: Array<
		Array<{
			date: Date;
			dateStr: string;
			data: HeatmapDay | undefined;
			inYear: boolean;
		}>
	> = [];
	const cursor = new Date(gridStart);

	for (let w = 0; w < 53; w++) {
		const week: (typeof weeks)[0] = [];
		for (let d = 0; d < 7; d++) {
			const dateStr = cursor.toISOString().slice(0, 10);
			week.push({
				date: new Date(cursor),
				dateStr,
				data: dataMap.get(dateStr),
				inYear: cursor.getFullYear() === year,
			});
			cursor.setDate(cursor.getDate() + 1);
		}
		weeks.push(week);
	}

	// Trim trailing weeks that are entirely outside the year
	while (weeks.length > 0 && weeks[weeks.length - 1].every((d) => !d.inYear)) {
		weeks.pop();
	}

	return weeks;
}

function getMonthLabels(weeks: ReturnType<typeof buildGrid>) {
	const labels: Array<{ month: string; col: number }> = [];
	let lastMonth = -1;

	for (let w = 0; w < weeks.length; w++) {
		const monday = weeks[w][0];
		if (monday.inYear) {
			const month = monday.date.getMonth();
			if (month !== lastMonth) {
				labels.push({ month: MONTH_NAMES[month], col: w });
				lastMonth = month;
			}
		}
	}

	return labels;
}

function formatTooltipDate(date: Date): string {
	return date.toLocaleDateString("en-US", {
		weekday: "short",
		month: "short",
		day: "numeric",
	});
}

interface ContributionHeatmapProps {
	projectId?: string;
	tag?: string;
}

export function ContributionHeatmap({ projectId, tag }: ContributionHeatmapProps) {
	const currentYear = new Date().getFullYear();
	const [year, setYear] = useState(currentYear);
	const { data: heatmapData, isLoading } = useHeatmap(year, projectId, tag);

	const weeks = buildGrid(year, heatmapData ?? []);
	const monthLabels = getMonthLabels(weeks);

	const totalMinutes = (heatmapData ?? []).reduce((sum, d) => sum + d.total_minutes, 0);
	const activeDays = (heatmapData ?? []).filter((d) => d.total_minutes > 0).length;
	const hasData = activeDays > 0;

	const todayStr = new Date().toISOString().slice(0, 10);
	const isCurrentYear = year === currentYear;

	return (
		<div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden">
			{/* Header */}
			<div className="flex items-center gap-2 px-4 py-2.5 border-b border-border/40">
				<button
					onClick={() => setYear((y) => y - 1)}
					className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary/50 transition-colors"
					aria-label="Previous year"
				>
					<ChevronLeft className="w-4 h-4" />
				</button>
				<span className="text-sm font-medium text-foreground min-w-[48px] text-center">{year}</span>
				<button
					onClick={() => setYear((y) => Math.min(y + 1, currentYear))}
					disabled={year >= currentYear}
					className={cn(
						"p-1 rounded-md transition-colors",
						year >= currentYear
							? "text-muted-foreground/30 cursor-not-allowed"
							: "text-muted-foreground hover:text-foreground hover:bg-secondary/50",
					)}
					aria-label="Next year"
				>
					<ChevronRight className="w-4 h-4" />
				</button>

				<div className="ml-auto flex items-center gap-4 text-xs text-muted-foreground">
					{hasData && (
						<>
							<span>
								<span className="text-foreground font-medium tabular-nums">{activeDays}</span>{" "}
								active days
							</span>
							<span>
								<span className="text-accent font-medium tabular-nums">
									{(totalMinutes / 60).toFixed(0)}h
								</span>{" "}
								total
							</span>
						</>
					)}
				</div>
			</div>

			{/* Grid */}
			<div className="px-4 py-3 overflow-x-auto">
				{isLoading ? (
					<div className="h-24 flex items-center justify-center text-muted-foreground text-xs">
						Loading...
					</div>
				) : (
					<div className="relative inline-flex flex-col gap-0.5">
						{/* Month labels */}
						<div className="flex ml-8 mb-1">
							{monthLabels.map((label, i) => {
								const nextCol = i + 1 < monthLabels.length ? monthLabels[i + 1].col : weeks.length;
								const span = nextCol - label.col;
								return (
									<span
										key={`${label.month}-${label.col}`}
										className="text-[10px] text-muted-foreground"
										style={{ width: `${span * 13}px` }}
									>
										{label.month}
									</span>
								);
							})}
						</div>

						{/* Day rows */}
						{Array.from({ length: 7 }, (_, dayIndex) => (
							<div key={dayIndex} className="flex items-center gap-0.5">
								<span className="text-[10px] text-muted-foreground w-7 text-right pr-1.5">
									{DAY_LABELS[dayIndex]}
								</span>
								{weeks.map((week, weekIndex) => {
									const cell = week[dayIndex];
									if (!cell.inYear) {
										return <div key={weekIndex} className="w-[11px] h-[11px]" />;
									}

									const minutes = cell.data?.total_minutes ?? 0;
									const intensity = getIntensity(minutes);
									const isToday = isCurrentYear && cell.dateStr === todayStr;

									return (
										<Tooltip key={weekIndex}>
											<TooltipTrigger asChild>
												<div
													className={cn(
														"w-[11px] h-[11px] rounded-[2px] transition-colors cursor-default",
														INTENSITY_CLASSES[intensity],
														isToday && "ring-1 ring-foreground/60",
													)}
												/>
											</TooltipTrigger>
											<TooltipContent side="top" className="text-xs px-2.5 py-1.5">
												<p className="font-medium text-popover-foreground">
													{formatTooltipDate(cell.date)}
												</p>
												{minutes > 0 ? (
													<p className="text-muted-foreground mt-0.5">
														{(minutes / 60).toFixed(1)}h &middot; {cell.data!.session_count} session
														{cell.data!.session_count !== 1 ? "s" : ""}
														{!projectId && (
															<>
																{" "}
																&middot; {cell.data!.project_count} project
																{cell.data!.project_count !== 1 ? "s" : ""}
															</>
														)}
													</p>
												) : (
													<p className="text-muted-foreground/60 mt-0.5">No activity</p>
												)}
											</TooltipContent>
										</Tooltip>
									);
								})}
							</div>
						))}

						{/* Legend */}
						<div className="flex items-center gap-1.5 ml-8 mt-2">
							<span className="text-[10px] text-muted-foreground">Less</span>
							{INTENSITY_CLASSES.map((cls, i) => (
								<div key={i} className={cn("w-[11px] h-[11px] rounded-[2px]", cls)} />
							))}
							<span className="text-[10px] text-muted-foreground">More</span>
						</div>

						{/* Empty state overlay */}
						{!hasData && !isLoading && (
							<div className="absolute inset-0 flex items-center justify-center pointer-events-none">
								<span className="text-xs text-muted-foreground/50 bg-card/80 px-3 py-1.5 rounded-md">
									Start tracking to see your activity here
								</span>
							</div>
						)}
					</div>
				)}
			</div>
		</div>
	);
}
