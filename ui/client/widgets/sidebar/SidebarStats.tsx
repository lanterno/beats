/**
 * Sidebar Stats Component
 * Shows today, this week (with comparison), and streak at a glance.
 */
import { Flame } from "lucide-react";
import { useAllCurrentWeekSessions, useLastWeekTotal, useStreaks } from "@/entities/session";

export function SidebarStats() {
	const { data: dailySummary } = useAllCurrentWeekSessions();
	const { data: streaks } = useStreaks();
	const { data: lastWeek } = useLastWeekTotal();

	const today = new Date();
	today.setHours(0, 0, 0, 0);

	const todayMinutes =
		dailySummary?.find((d) => d.date.toDateString() === today.toDateString())?.totalMinutes ?? 0;
	const weekMinutes = dailySummary?.reduce((sum, d) => sum + d.totalMinutes, 0) ?? 0;

	const todayHours = (todayMinutes / 60).toFixed(1);
	const weekHours = (weekMinutes / 60).toFixed(1);

	// Weekly comparison
	const lastWeekMinutes = lastWeek?.lastWeekMinutes ?? 0;
	let weekChange: { pct: number; direction: "up" | "down" } | null = null;
	if (lastWeekMinutes > 0 && weekMinutes > 0) {
		const pct = Math.round(((weekMinutes - lastWeekMinutes) / lastWeekMinutes) * 100);
		if (pct !== 0) {
			weekChange = { pct: Math.abs(pct), direction: pct > 0 ? "up" : "down" };
		}
	}

	const currentStreak = streaks?.current ?? 0;
	const longestStreak = streaks?.longest ?? 0;

	return (
		<div className="space-y-2">
			<div className="grid grid-cols-2 gap-2">
				<div className="rounded-md border border-border/60 bg-secondary/30 px-3 py-2.5 text-center">
					<p className="text-muted-foreground text-[10px] uppercase tracking-[0.14em] mb-0.5">
						Today
					</p>
					<p className="font-heading text-lg font-semibold tabular-nums text-foreground">
						{todayHours}h
					</p>
				</div>
				<div className="rounded-md border border-border/60 bg-secondary/30 px-3 py-2.5 text-center">
					<p className="text-muted-foreground text-[10px] uppercase tracking-[0.14em] mb-0.5">
						This week
					</p>
					<p className="font-heading text-lg font-semibold tabular-nums text-accent">
						{weekHours}h
					</p>
					{weekChange && (
						<p className="text-[10px] tabular-nums text-muted-foreground mt-0.5">
							<span
								className={weekChange.direction === "up" ? "text-success" : "text-muted-foreground"}
							>
								{weekChange.direction === "up" ? "\u2191" : "\u2193"} {weekChange.pct}%
							</span>{" "}
							vs last wk
						</p>
					)}
				</div>
			</div>

			{currentStreak > 0 && (
				<div className="flex items-center justify-center gap-1.5 rounded-md border border-border/60 bg-secondary/30 px-3 py-1.5">
					<Flame className="w-3.5 h-3.5 text-accent" />
					<span className="text-xs text-foreground">
						<span className="font-medium tabular-nums">{currentStreak}</span>
						-day streak
					</span>
					{longestStreak > currentStreak && (
						<span className="text-[10px] text-muted-foreground ml-1">Best: {longestStreak}</span>
					)}
				</div>
			)}
		</div>
	);
}
