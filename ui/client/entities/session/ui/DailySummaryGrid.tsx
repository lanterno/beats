/**
 * Daily Summary Grid Component
 * Displays a week's worth of daily summaries.
 */
import { formatDuration } from "@/shared/lib";
import type { DaySummary } from "../model";

interface DailySummaryGridProps {
	dailySummary: DaySummary[];
	showSessionCount?: boolean;
	showDateShort?: boolean;
	showWeekTotal?: boolean;
	compact?: boolean;
}

export function DailySummaryGrid({
	dailySummary,
	showSessionCount = false,
	showDateShort = false,
	showWeekTotal = false,
	compact = false,
}: DailySummaryGridProps) {
	const weekTotal = dailySummary.reduce((sum, day) => sum + day.totalMinutes, 0);

	return (
		<div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden">
			<div className="grid grid-cols-1 md:grid-cols-7 gap-2.5 p-4">
				{dailySummary.map((day, index) => {
					const isToday = day.date.toDateString() === new Date().toDateString();
					const hours = day.totalMinutes / 60;
					const dayLabel = day.dayName?.slice(0, 3) ?? "";

					return (
						<div
							key={index}
							className={`
                rounded-md p-3 border text-center transition-colors duration-150
                ${
									isToday
										? "border-accent/30 bg-accent/10"
										: day.totalMinutes > 0
											? "border-border bg-secondary/50"
											: "border-border/30 bg-transparent"
								}
              `}
						>
							{isToday && <div className="w-1.5 h-1.5 rounded-full bg-accent mx-auto mb-1" />}
							<div className="text-xs uppercase tracking-widest text-muted-foreground mb-1">
								{dayLabel}
							</div>
							{showDateShort && day.dateShort && (
								<div className="text-sm text-muted-foreground/90 mb-1.5">{day.dateShort}</div>
							)}
							<div
								className={`font-medium tabular-nums text-base ${hours > 0 ? "text-foreground" : "text-muted-foreground/50"} ${isToday && hours > 0 ? "text-accent" : ""}`}
							>
								{hours > 0 ? hours.toFixed(1) : "0"}h
							</div>
							{day.totalMinutes > 0 && !compact && (
								<div className="text-xs text-muted-foreground/80 mt-0.5">
									{day.totalMinutes.toFixed(0)}m
								</div>
							)}
							{showSessionCount && day.sessionCount !== undefined && day.sessionCount > 0 && (
								<div className="text-xs text-muted-foreground/75 mt-0.5">
									{day.sessionCount} session
									{day.sessionCount !== 1 ? "s" : ""}
								</div>
							)}
						</div>
					);
				})}
			</div>
			{showWeekTotal && (
				<div className="px-4 py-3.5 border-t border-border/60 flex justify-between items-center">
					<span className="text-muted-foreground text-xs uppercase tracking-[0.12em]">
						Week total
					</span>
					<span className="font-medium text-accent text-base tabular-nums">
						{formatDuration(weekTotal)}
					</span>
				</div>
			)}
		</div>
	);
}
