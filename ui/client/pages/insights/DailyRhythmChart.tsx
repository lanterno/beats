/**
 * DailyRhythmChart Component
 * 24-hour bar chart showing when you typically work.
 */
import { useState } from "react";
import { useDailyRhythm } from "@/entities/session";
import { cn } from "@/shared/lib";
import { EmptyState, Panel, Tooltip, TooltipContent, TooltipTrigger } from "@/shared/ui";
import { LABEL, SEG, SEG_BUTTON, SEG_OFF, SEG_ON } from "./styles";

type Period = "week" | "month" | "all";

const PERIOD_LABELS: Record<Period, string> = {
	week: "This Week",
	month: "This Month",
	all: "All Time",
};

const HOUR_LABELS = [0, 3, 6, 9, 12, 15, 18, 21];

function formatSlotTime(slot: number): string {
	const hour = Math.floor(slot / 2);
	const min = slot % 2 === 0 ? "00" : "30";
	return `${hour}:${min}`;
}

interface DailyRhythmChartProps {
	projectId?: string;
	tag?: string;
}

export function DailyRhythmChart({ projectId, tag }: DailyRhythmChartProps) {
	const [period, setPeriod] = useState<Period>("month");
	const { data: rhythmData, isLoading } = useDailyRhythm(period, projectId, tag);

	const slots = rhythmData ?? [];
	const maxMinutes = Math.max(...slots.map((s) => s.minutes), 1);
	const hasData = slots.some((s) => s.minutes > 0);

	return (
		<Panel padding="px-6 py-[22px]">
			{/* Header */}
			<div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
				<span className={LABEL}>Daily Rhythm</span>
				<div className={SEG}>
					{(["week", "month", "all"] as Period[]).map((p) => (
						<button
							type="button"
							key={p}
							onClick={() => setPeriod(p)}
							className={cn(SEG_BUTTON, period === p ? SEG_ON : SEG_OFF)}
						>
							{PERIOD_LABELS[p]}
						</button>
					))}
				</div>
			</div>

			{/* Chart */}
			<div className="mt-4">
				{isLoading ? (
					<div className="h-28 flex items-center justify-center text-muted-foreground text-xs">
						Loading...
					</div>
				) : !hasData ? (
					<EmptyState variant="chart" message="No sessions recorded for this period" />
				) : (
					<div>
						{/* Bars */}
						<div className="flex items-end gap-px h-28">
							{slots.map((slot) => {
								const height =
									slot.minutes > 0 ? Math.max((slot.minutes / maxMinutes) * 100, 2) : 0;

								return (
									<Tooltip key={slot.slot}>
										<TooltipTrigger asChild>
											<div className="flex-1 h-full flex items-end justify-center cursor-default">
												<div
													className={cn(
														"w-full rounded-t-[3px] transition-all",
														slot.minutes > 0 ? "bg-success/55 hover:bg-success" : "bg-transparent",
													)}
													style={{ height: `${height}%` }}
												/>
											</div>
										</TooltipTrigger>
										{slot.minutes > 0 && (
											<TooltipContent side="top" className="text-xs px-2.5 py-1.5">
												<p className="font-medium">
													{formatSlotTime(slot.slot)} — {formatSlotTime(slot.slot + 1)}
												</p>
												<p className="text-muted-foreground mt-0.5">
													{slot.minutes.toFixed(1)} min avg
												</p>
											</TooltipContent>
										)}
									</Tooltip>
								);
							})}
						</div>

						{/* Hour labels */}
						<div className="flex mt-1.5">
							{Array.from({ length: 48 }, (_, i) => {
								const hour = Math.floor(i / 2);
								const isLabeled = HOUR_LABELS.includes(hour) && i % 2 === 0;
								return (
									<div key={i} className="flex-1 text-center">
										{isLabeled && (
											<span className="text-[9.5px] font-bold font-mono tabular-nums text-muted-foreground whitespace-nowrap">
												{hour}
											</span>
										)}
									</div>
								);
							})}
						</div>
					</div>
				)}
			</div>
		</Panel>
	);
}
