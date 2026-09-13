/**
 * YearInReview Page
 * Typographic poster summarizing a year's time tracking data.
 * Total hours, project rankings, busiest month, longest streak,
 * work hour distribution.
 */

import { useQuery } from "@tanstack/react-query";
import { Check, ChevronLeft, ChevronRight, Copy } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { useProjects } from "@/entities/project";
import { fetchBeats, sessionKeys, toSession, useHeatmap } from "@/entities/session";
import { formatDuration, parseUtcIso } from "@/shared/lib";
import { Button, EmptyState, Panel } from "@/shared/ui";
import { CHIP, SKY_CHIP, SKY_ROUND } from "./styles";

const MONTH_NAMES = [
	"January",
	"February",
	"March",
	"April",
	"May",
	"June",
	"July",
	"August",
	"September",
	"October",
	"November",
	"December",
];
const MONTH_SHORT = [
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

function useYearSessions(year: number) {
	return useQuery({
		queryKey: [...sessionKeys.all, "year-review", year],
		queryFn: async () => {
			const beats = await fetchBeats();
			return beats
				.filter((b) => b.start && b.end)
				.map(toSession)
				.filter((s) => {
					const d = parseUtcIso(s.startTime);
					return d.getFullYear() === year;
				});
		},
		staleTime: 120_000,
	});
}

export default function YearInReview() {
	const { year: yearParam } = useParams<{ year: string }>();
	const navigate = useNavigate();
	const [copied, setCopied] = useState(false);

	const now = new Date();
	const year = yearParam ? parseInt(yearParam, 10) : now.getFullYear() - 1;

	const { data: sessions, isLoading } = useYearSessions(year);
	const { data: heatmapData } = useHeatmap(year);
	const { data: projects } = useProjects();

	const projectMap = new Map((projects ?? []).map((p) => [p.id, { name: p.name, color: p.color }]));

	const stats = useMemo(() => {
		if (!sessions || sessions.length === 0) return null;

		const totalMinutes = sessions.reduce((sum, s) => sum + s.duration, 0);

		// By month
		const byMonth = new Map<number, number>();
		for (const s of sessions) {
			const m = parseUtcIso(s.startTime).getMonth();
			byMonth.set(m, (byMonth.get(m) || 0) + s.duration);
		}
		const monthlyMinutes = Array.from({ length: 12 }, (_, i) => byMonth.get(i) ?? 0);
		const busiestMonthIdx = monthlyMinutes.indexOf(Math.max(...monthlyMinutes));
		const maxMonthMinutes = Math.max(...monthlyMinutes, 1);

		// By project
		const byProject = new Map<string, number>();
		for (const s of sessions) {
			byProject.set(s.projectId, (byProject.get(s.projectId) || 0) + s.duration);
		}
		const projectRankings = [...byProject.entries()]
			.sort((a, b) => b[1] - a[1])
			.map(([id, minutes], rank) => ({
				rank: rank + 1,
				id,
				minutes,
				name: projectMap.get(id)?.name ?? "Unknown",
				color: projectMap.get(id)?.color ?? "var(--color-muted-foreground)",
			}));

		// Work hours distribution (24-hour)
		const hourBuckets = new Array(24).fill(0);
		for (const s of sessions) {
			const startHour = parseUtcIso(s.startTime).getHours();
			hourBuckets[startHour] += s.duration;
		}
		const peakHour = hourBuckets.indexOf(Math.max(...hourBuckets));

		// Active days from heatmap
		const activeDays = heatmapData ? heatmapData.filter((d) => d.total_minutes > 0).length : 0;

		// Longest streak from heatmap data
		let longestStreak = 0;
		if (heatmapData) {
			const activeDates = new Set(
				heatmapData.filter((d) => d.total_minutes > 0).map((d) => d.date),
			);
			let current = 0;
			// Walk every day of the year
			const start = new Date(year, 0, 1);
			const end = new Date(year, 11, 31);
			for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
				const key = d.toISOString().slice(0, 10);
				if (activeDates.has(key)) {
					current++;
					longestStreak = Math.max(longestStreak, current);
				} else {
					current = 0;
				}
			}
		}

		// Busiest day
		let busiestDay = { date: "", minutes: 0 };
		if (heatmapData) {
			for (const d of heatmapData) {
				if (d.total_minutes > busiestDay.minutes) {
					busiestDay = { date: d.date, minutes: d.total_minutes };
				}
			}
		}

		// Tags
		const tagCounts = new Map<string, number>();
		for (const s of sessions) {
			for (const tag of s.tags) {
				tagCounts.set(tag, (tagCounts.get(tag) || 0) + 1);
			}
		}
		const topTags = [...tagCounts.entries()]
			.sort((a, b) => b[1] - a[1])
			.slice(0, 8)
			.map(([tag, count]) => ({ tag, count }));

		return {
			totalMinutes,
			sessionCount: sessions.length,
			activeDays,
			longestStreak,
			busiestMonthIdx,
			busiestDay,
			monthlyMinutes,
			maxMonthMinutes,
			projectRankings,
			hourBuckets,
			peakHour,
			topTags,
		};
	}, [sessions, heatmapData, projectMap, year]);

	const handleCopy = () => {
		if (!stats) return;
		const lines = [
			`${year} Year in Review`,
			`Total: ${formatDuration(stats.totalMinutes)}`,
			`Sessions: ${stats.sessionCount}`,
			`Active days: ${stats.activeDays}`,
			`Longest streak: ${stats.longestStreak} days`,
			`Busiest month: ${MONTH_NAMES[stats.busiestMonthIdx]}`,
			"",
			"Project Rankings:",
			...stats.projectRankings
				.slice(0, 5)
				.map((p) => `  ${p.rank}. ${p.name} — ${formatDuration(p.minutes)}`),
		].join("\n");
		navigator.clipboard.writeText(lines);
		setCopied(true);
		setTimeout(() => setCopied(false), 2000);
		toast.success("Summary copied");
	};

	const isCurrentYear = year >= now.getFullYear();

	return (
		<div className="max-w-2xl mx-auto px-6 py-8">
			{/* Navigation */}
			<div className="flex items-center justify-between mb-8">
				<div className="flex items-center gap-3">
					<Link to="/insights" className={SKY_CHIP}>
						Insights
					</Link>
					<span className="text-muted-foreground">/</span>
					<span className="text-sm text-foreground">Year in Review</span>
				</div>
				<div className="flex items-center gap-2">
					<button
						type="button"
						onClick={() => navigate(`/insights/year/${year - 1}`)}
						className={SKY_ROUND}
					>
						<ChevronLeft className="w-4 h-4" />
					</button>
					<button
						type="button"
						onClick={() => navigate(`/insights/year/${year + 1}`)}
						disabled={isCurrentYear}
						className={SKY_ROUND}
					>
						<ChevronRight className="w-4 h-4" />
					</button>
				</div>
			</div>

			{isLoading ? (
				<div className="h-40 flex items-center justify-center text-muted-foreground text-sm">
					Loading...
				</div>
			) : !stats ? (
				<EmptyState variant="chart" message={`No sessions tracked in ${year}`} />
			) : (
				<Panel padding="px-6 py-10 sm:px-10" className="space-y-10">
					{/* Title section */}
					<div className="text-center space-y-2">
						<p className="text-[10.5px] font-bold uppercase tracking-[0.3em] text-muted-foreground">
							Year in Review
						</p>
						<h1 className="font-heading text-6xl font-extrabold tracking-[-0.02em] text-foreground tabular-nums">
							{year}
						</h1>
					</div>

					{/* Big stats */}
					<div className="grid grid-cols-2 gap-6 text-center">
						<div>
							<p className="font-heading text-2xl sm:text-3xl font-bold text-foreground tabular-nums">
								{formatDuration(stats.totalMinutes)}
							</p>
							<p className="text-xs font-medium text-muted-foreground mt-1">Total tracked</p>
						</div>
						<div>
							<p className="font-heading text-2xl sm:text-3xl font-bold text-foreground tabular-nums">
								{stats.sessionCount.toLocaleString()}
							</p>
							<p className="text-xs font-medium text-muted-foreground mt-1">Sessions</p>
						</div>
						<div>
							<p className="font-heading text-2xl sm:text-3xl font-bold text-foreground tabular-nums">
								{stats.activeDays}
							</p>
							<p className="text-xs font-medium text-muted-foreground mt-1">Active days</p>
						</div>
						<div>
							<p className="font-heading text-2xl sm:text-3xl font-bold text-foreground tabular-nums">
								{stats.longestStreak}
							</p>
							<p className="text-xs font-medium text-muted-foreground mt-1">Longest streak</p>
						</div>
					</div>

					{/* Monthly chart */}
					<div>
						<p className="text-[10.5px] font-bold uppercase tracking-[0.2em] text-muted-foreground mb-3 text-center">
							Month by Month
						</p>
						<div className="flex items-end justify-center gap-1.5 h-32">
							{stats.monthlyMinutes.map((minutes, i) => (
								<div key={i} className="flex flex-col items-center gap-1 flex-1">
									<span className="hidden sm:block text-[9px] font-bold font-mono text-muted-foreground tabular-nums">
										{minutes > 0 ? formatDuration(minutes) : ""}
									</span>
									<div
										className="w-full rounded-t-[4px] transition-all"
										style={{
											height: `${Math.max((minutes / stats.maxMonthMinutes) * 80, 2)}px`,
											backgroundColor:
												i === stats.busiestMonthIdx
													? "hsl(var(--success))"
													: minutes > 0
														? "hsl(var(--success) / 0.4)"
														: "hsl(var(--muted))",
										}}
									/>
									<span
										className={`text-[9px] ${i === stats.busiestMonthIdx ? "text-foreground font-bold" : "text-muted-foreground font-medium"}`}
									>
										{MONTH_SHORT[i]}
									</span>
								</div>
							))}
						</div>
					</div>

					{/* Project rankings */}
					<div>
						<p className="text-[10.5px] font-bold uppercase tracking-[0.2em] text-muted-foreground mb-4 text-center">
							Project Rankings
						</p>
						<div className="space-y-2.5">
							{stats.projectRankings.map((p) => {
								const pct = (p.minutes / stats.totalMinutes) * 100;
								return (
									<div key={p.id} className="flex items-center gap-3">
										<span className="text-lg font-heading font-bold text-muted-foreground w-8 text-right tabular-nums">
											{p.rank}
										</span>
										<div
											className="w-3 h-3 rounded-full shrink-0"
											style={{ backgroundColor: p.color }}
										/>
										<span className="text-sm text-foreground font-medium truncate flex-1 min-w-0">
											{p.name}
										</span>
										<span className="text-sm font-bold font-mono tabular-nums text-foreground shrink-0">
											{formatDuration(p.minutes)}
										</span>
										<span className="text-[10px] font-medium text-muted-foreground w-10 text-right shrink-0">
											{pct.toFixed(0)}%
										</span>
									</div>
								);
							})}
						</div>
					</div>

					{/* Busiest day */}
					{stats.busiestDay.minutes > 0 && (
						<div className="text-center space-y-1">
							<p className="text-[10.5px] font-bold uppercase tracking-[0.2em] text-muted-foreground">
								Busiest Day
							</p>
							<p className="font-heading text-lg font-semibold text-foreground">
								{new Date(`${stats.busiestDay.date}T12:00:00`).toLocaleDateString(undefined, {
									weekday: "long",
									month: "long",
									day: "numeric",
								})}
							</p>
							<p className="text-foreground font-bold font-mono text-sm">
								{formatDuration(stats.busiestDay.minutes)}
							</p>
						</div>
					)}

					{/* Work hours distribution */}
					<div>
						<p className="text-[10.5px] font-bold uppercase tracking-[0.2em] text-muted-foreground mb-3 text-center">
							When You Work
						</p>
						<div className="flex items-end justify-center gap-px h-16">
							{stats.hourBuckets.map((minutes, h) => {
								const max = Math.max(...stats.hourBuckets, 1);
								return (
									<div
										key={h}
										className="flex-1 rounded-t-[3px] transition-all"
										style={{
											height: `${Math.max((minutes / max) * 56, 1)}px`,
											backgroundColor:
												h === stats.peakHour
													? "hsl(var(--success))"
													: minutes > 0
														? "hsl(var(--success) / 0.4)"
														: "hsl(var(--muted))",
										}}
										title={`${h}:00 — ${formatDuration(minutes)}`}
									/>
								);
							})}
						</div>
						<div className="flex justify-between mt-1">
							<span className="text-[9.5px] font-bold font-mono text-muted-foreground">12 AM</span>
							<span className="text-[9.5px] font-bold font-mono text-muted-foreground">6 AM</span>
							<span className="text-[9.5px] font-bold font-mono text-muted-foreground">12 PM</span>
							<span className="text-[9.5px] font-bold font-mono text-muted-foreground">6 PM</span>
							<span className="text-[9.5px] font-bold font-mono text-muted-foreground">12 AM</span>
						</div>
						<p className="text-xs font-medium text-muted-foreground text-center mt-2">
							Peak hour: <span className="text-foreground font-bold">{stats.peakHour}:00</span>
						</p>
					</div>

					{/* Tags */}
					{stats.topTags.length > 0 && (
						<div className="text-center">
							<p className="text-[10.5px] font-bold uppercase tracking-[0.2em] text-muted-foreground mb-3">
								Top Tags
							</p>
							<div className="flex flex-wrap justify-center gap-2">
								{stats.topTags.map(({ tag, count }) => (
									<span key={tag} className={CHIP}>
										{tag}
										<span className="text-muted-foreground text-[10px]">{count}</span>
									</span>
								))}
							</div>
						</div>
					)}

					{/* Footer */}
					<div className="text-center pt-5 border-t border-border space-y-3">
						<p className="text-[10px] font-bold text-muted-foreground tracking-[0.3em] uppercase">
							Beats
						</p>
						<Button
							variant="secondary"
							size="sm"
							onClick={handleCopy}
							className="h-8 px-3.5 text-xs"
						>
							{copied ? (
								<>
									<Check className="w-3.5 h-3.5 text-success" /> Copied
								</>
							) : (
								<>
									<Copy className="w-3.5 h-3.5" /> Copy summary
								</>
							)}
						</Button>
					</div>
				</Panel>
			)}
		</div>
	);
}
