/**
 * WeeklyCard Component
 * Shareable visual summary card rendered as an SVG-styled div.
 * Shows project breakdown, hours, streak, and goal completion.
 */

import { Check, Copy } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { useProjects } from "@/entities/project";
import { useStreaks, useThisWeekSessions } from "@/entities/session";
import { formatDuration, getWeekRange, parseUtcIso } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { LABEL, SKY_BUTTON } from "./styles";

export function WeeklyCard() {
	const { data: projects } = useProjects();
	const { data: weekSessions } = useThisWeekSessions();
	const { data: streaks } = useStreaks();

	const projectMap = new Map((projects ?? []).map((p) => [p.id, { name: p.name, color: p.color }]));

	const stats = useMemo(() => {
		const sessions = weekSessions ?? [];
		const totalMinutes = sessions.reduce((sum, s) => sum + s.duration, 0);
		const sessionCount = sessions.length;

		// By project
		const byProject = new Map<string, number>();
		for (const s of sessions) {
			byProject.set(s.projectId, (byProject.get(s.projectId) || 0) + s.duration);
		}
		const projectBreakdown = [...byProject.entries()]
			.sort((a, b) => b[1] - a[1])
			.map(([id, minutes]) => ({
				id,
				minutes,
				name: projectMap.get(id)?.name ?? "Unknown",
				color: projectMap.get(id)?.color ?? "var(--color-muted-foreground)",
			}));

		// Day breakdown for mini chart
		const { start: weekStart } = getWeekRange(0);
		const dayMinutes = Array.from({ length: 7 }, (_, i) => {
			const d = new Date(weekStart);
			d.setDate(weekStart.getDate() + i);
			d.setHours(0, 0, 0, 0);
			const dEnd = new Date(d);
			dEnd.setHours(23, 59, 59, 999);
			return sessions
				.filter((s) => {
					const sd = parseUtcIso(s.startTime);
					return sd >= d && sd <= dEnd;
				})
				.reduce((sum, s) => sum + s.duration, 0);
		});

		// Goals
		const goalsMetCount = (projects ?? []).filter((p) => {
			if (!p.weeklyGoal || p.archived) return false;
			const projectMinutes = byProject.get(p.id) ?? 0;
			return projectMinutes >= p.weeklyGoal * 60;
		}).length;
		const goalsTotal = (projects ?? []).filter((p) => p.weeklyGoal && !p.archived).length;

		return {
			totalMinutes,
			sessionCount,
			projectBreakdown,
			dayMinutes,
			goalsMetCount,
			goalsTotal,
		};
	}, [weekSessions, projects, projectMap]);

	const { start: weekStart, end: weekEnd } = getWeekRange(0);
	const weekLabel = `${weekStart.toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${weekEnd.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;

	const maxDayMinutes = Math.max(...stats.dayMinutes, 1);
	const dayLabels = ["M", "T", "W", "T", "F", "S", "S"];

	const [isCopied, setIsCopied] = useState(false);

	const handleCopy = () => {
		const lines = [
			`Weekly Summary — ${weekLabel}`,
			`Total: ${formatDuration(stats.totalMinutes)} (${stats.sessionCount} sessions)`,
			streaks && streaks.current > 0 ? `Streak: ${streaks.current} days` : "",
			"",
			...stats.projectBreakdown.slice(0, 5).map((p) => `  ${p.name}: ${formatDuration(p.minutes)}`),
			stats.goalsTotal > 0 ? `\nGoals: ${stats.goalsMetCount}/${stats.goalsTotal} met` : "",
		]
			.filter(Boolean)
			.join("\n");
		navigator.clipboard.writeText(lines);
		setIsCopied(true);
		setTimeout(() => setIsCopied(false), 2000);
		toast.success("Summary copied to clipboard");
	};

	return (
		<div className="space-y-3">
			{/* The card */}
			<Panel className="max-w-sm mx-auto">
				{/* Header */}
				<div className="text-center mb-4">
					<p className={`${LABEL} mb-0.5`}>Weekly Summary</p>
					<p className="text-xs font-medium text-muted-foreground">{weekLabel}</p>
				</div>

				{/* Big number */}
				<div className="text-center mb-4">
					<p className="font-heading text-3xl font-extrabold tracking-[-0.02em] text-foreground tabular-nums">
						{formatDuration(stats.totalMinutes)}
					</p>
					<p className="text-xs font-medium text-muted-foreground mt-0.5">
						{stats.sessionCount} session{stats.sessionCount !== 1 ? "s" : ""}
						{streaks && streaks.current > 0 && (
							<span className="ml-2 text-foreground font-bold">{streaks.current}-day streak</span>
						)}
					</p>
				</div>

				{/* Mini day chart */}
				<div className="flex items-end justify-center gap-1.5 h-12 mb-4">
					{stats.dayMinutes.map((minutes, i) => (
						<div key={i} className="flex flex-col items-center gap-0.5">
							<div
								className="w-5 rounded-t-[5px] rounded-b-[2px] transition-all"
								style={{
									height: `${Math.max((minutes / maxDayMinutes) * 40, 2)}px`,
									backgroundColor: minutes > 0 ? "hsl(var(--success) / 0.7)" : "hsl(var(--muted))",
								}}
							/>
							<span className="text-[9.5px] font-bold font-mono text-muted-foreground">
								{dayLabels[i]}
							</span>
						</div>
					))}
				</div>

				{/* Project breakdown */}
				{stats.projectBreakdown.length > 0 && (
					<div className="space-y-1.5 mb-3">
						{stats.projectBreakdown.slice(0, 5).map((p) => (
							<div key={p.id} className="flex items-center gap-2">
								<div
									className="w-2 h-2 rounded-full shrink-0"
									style={{ backgroundColor: p.color }}
								/>
								<span className="text-xs font-medium text-foreground truncate flex-1">
									{p.name}
								</span>
								<span className="text-xs font-bold font-mono tabular-nums text-foreground">
									{formatDuration(p.minutes)}
								</span>
							</div>
						))}
					</div>
				)}

				{/* Goals */}
				{stats.goalsTotal > 0 && (
					<div className="text-center pt-2.5 border-t border-border">
						<p className="text-xs font-medium text-muted-foreground">
							Goals:{" "}
							<span className="text-foreground font-bold">
								{stats.goalsMetCount}/{stats.goalsTotal}
							</span>{" "}
							met
						</p>
					</div>
				)}

				{/* Branding */}
				<div className="text-center mt-3">
					<p className="text-[9px] font-bold text-muted-foreground tracking-widest uppercase">
						Beats
					</p>
				</div>
			</Panel>

			{/* Actions */}
			<div className="flex justify-center gap-2">
				<button type="button" onClick={handleCopy} className={SKY_BUTTON}>
					{isCopied ? (
						<>
							<Check className="w-3.5 h-3.5 text-success" /> Copied
						</>
					) : (
						<>
							<Copy className="w-3.5 h-3.5" /> Copy summary
						</>
					)}
				</button>
			</div>
		</div>
	);
}
