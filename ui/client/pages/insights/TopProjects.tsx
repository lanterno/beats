/**
 * TopProjects Component
 * Horizontal bar chart showing hours per project for a period.
 */
import { useState } from "react";
import { useNavigate } from "react-router";
import { useProjects } from "@/entities/project";
import { useProjectBreakdown } from "@/entities/session";
import { cn, formatDuration } from "@/shared/lib";
import { EmptyState, Panel } from "@/shared/ui";
import { LABEL, SEG, SEG_BUTTON, SEG_OFF, SEG_ON } from "./styles";

type Period = "week" | "month" | "year" | "all";

const PERIOD_LABELS: Record<Period, string> = {
	week: "This Week",
	month: "This Month",
	year: "This Year",
	all: "All Time",
};

export function TopProjects({ tag }: { tag?: string }) {
	const navigate = useNavigate();
	const [period, setPeriod] = useState<Period>("month");
	const { data: breakdown, isLoading } = useProjectBreakdown(period, tag);
	const { data: projects } = useProjects();

	const projectMap = new Map((projects ?? []).map((p) => [p.id, { name: p.name, color: p.color }]));

	const items = (breakdown ?? [])
		.map((b) => {
			const proj = projectMap.get(b.projectId);
			if (!proj) return null;
			return { ...b, name: proj.name, color: proj.color };
		})
		.filter(Boolean) as Array<{
		projectId: string;
		minutes: number;
		name: string;
		color: string;
	}>;

	const maxMinutes = items.length > 0 ? items[0].minutes : 1;
	const totalMinutes = items.reduce((sum, i) => sum + i.minutes, 0);

	return (
		<Panel padding="px-6 py-[22px]">
			{/* Header */}
			<div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
				<span className={LABEL}>Top Projects</span>
				<div className={SEG}>
					{(["week", "month", "year", "all"] as Period[]).map((p) => (
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

			{/* Content */}
			<div className="mt-4">
				{isLoading ? (
					<div className="h-20 flex items-center justify-center text-muted-foreground text-xs">
						Loading...
					</div>
				) : items.length === 0 ? (
					<EmptyState variant="seedling" message="Track some time to see your project breakdown" />
				) : (
					<div className="space-y-2">
						{items.map((item) => {
							const barWidth = (item.minutes / maxMinutes) * 100;

							return (
								<button
									type="button"
									key={item.projectId}
									onClick={() => navigate(`/project/${item.projectId}`)}
									className="w-full flex items-center gap-2.5 px-2 py-1 rounded-xl hover:bg-secondary transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
								>
									<div
										className="w-2 h-2 rounded-full shrink-0"
										style={{ backgroundColor: item.color }}
									/>
									<span className="text-xs font-medium text-foreground truncate min-w-0 w-28 shrink-0 text-left">
										{item.name}
									</span>
									<div className="flex-1 h-2 rounded-full bg-muted">
										<div
											className="h-full rounded-full transition-all duration-300"
											style={{
												width: `${barWidth}%`,
												backgroundColor: `color-mix(in srgb, ${item.color} 70%, transparent)`,
											}}
										/>
									</div>
									<span className="text-xs font-bold font-mono tabular-nums text-foreground shrink-0 w-20 whitespace-nowrap text-right">
										{formatDuration(item.minutes)}
									</span>
								</button>
							);
						})}

						{/* Total footer */}
						<div className="flex items-center justify-end pt-2.5 border-t border-border">
							<span className={`${LABEL} mr-2`}>Total</span>
							<span className="text-sm font-bold font-mono tabular-nums text-foreground">
								{formatDuration(totalMinutes)}
							</span>
						</div>
					</div>
				)}
			</div>
		</Panel>
	);
}
