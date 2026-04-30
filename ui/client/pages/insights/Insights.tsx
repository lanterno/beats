/**
 * Insights Page
 * Analytics dashboard with summary stats, contribution heatmap,
 * daily rhythm chart, and top projects breakdown.
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useProjects } from "@/entities/project";
import { useAllTags, useHeatmap } from "@/entities/session";
import { formatDuration } from "@/shared/lib";
import { ContributionHeatmap } from "./ContributionHeatmap";
import { DailyRhythmChart } from "./DailyRhythmChart";
import { EstimationAccuracy } from "./EstimationAccuracy";
import { FlowByLanguage } from "./FlowByLanguage";
import { FlowByRepo } from "./FlowByRepo";
import { FlowThisWeek } from "./FlowThisWeek";
import { FlowToday } from "./FlowToday";
import { MoodCorrelation } from "./MoodCorrelation";
import { PatternCards } from "./PatternCards";
import { ProjectHealth } from "./ProjectHealth";
import { TopProjects } from "./TopProjects";
import { WeeklyCard } from "./WeeklyCard";

export default function Insights() {
	const [selectedProjectId, setSelectedProjectId] = useState<string | undefined>(undefined);
	const [selectedTag, setSelectedTag] = useState<string | undefined>(undefined);
	const { data: projects } = useProjects();
	const { data: allTags } = useAllTags();
	const currentYear = new Date().getFullYear();
	const { data: heatmapData } = useHeatmap(currentYear, selectedProjectId, selectedTag);

	const activeProjects = (projects ?? []).filter((p) => !p.archived);

	// Compute current month summary from heatmap data
	const monthSummary = useMemo(() => {
		if (!heatmapData) return null;
		const now = new Date();
		const monthPrefix = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
		const monthDays = heatmapData.filter((d) => d.date.startsWith(monthPrefix));

		const totalMinutes = monthDays.reduce((sum, d) => sum + d.total_minutes, 0);
		const totalSessions = monthDays.reduce((sum, d) => sum + d.session_count, 0);
		const activeDays = monthDays.filter((d) => d.total_minutes > 0).length;
		const daysElapsed = now.getDate();
		const avgDailyMinutes = daysElapsed > 0 ? totalMinutes / daysElapsed : 0;

		return { totalMinutes, totalSessions, activeDays, avgDailyMinutes };
	}, [heatmapData]);

	return (
		<div className="max-w-5xl mx-auto px-6 py-6 space-y-5">
			{/* Header with project filter */}
			<div className="flex items-center justify-between">
				<div className="flex items-center gap-3">
					<h1 className="font-heading text-xl text-foreground">Insights</h1>
					<Link
						to="/insights/digests"
						className="text-[10px] px-2 py-0.5 rounded-full border border-accent/30 text-accent hover:bg-accent/10 transition-colors"
					>
						Digests
					</Link>
					<Link
						to={`/insights/year/${new Date().getFullYear() - 1}`}
						className="text-[10px] px-2 py-0.5 rounded-full border border-accent/30 text-accent hover:bg-accent/10 transition-colors"
					>
						{new Date().getFullYear() - 1} Review
					</Link>
				</div>
				<div className="flex items-center gap-2">
					{allTags && allTags.length > 0 && (
						<select
							value={selectedTag ?? ""}
							onChange={(e) => setSelectedTag(e.target.value || undefined)}
							className="text-xs bg-secondary/50 border border-border rounded-md px-2.5 py-1.5 text-foreground focus:outline-none focus:ring-1 focus:ring-accent"
						>
							<option value="">All Tags</option>
							{allTags.map((tag) => (
								<option key={tag} value={tag}>
									{tag}
								</option>
							))}
						</select>
					)}
					<select
						value={selectedProjectId ?? ""}
						onChange={(e) => setSelectedProjectId(e.target.value || undefined)}
						className="text-xs bg-secondary/50 border border-border rounded-md px-2.5 py-1.5 text-foreground focus:outline-none focus:ring-1 focus:ring-accent"
					>
						<option value="">All Projects</option>
						{activeProjects.map((p) => (
							<option key={p.id} value={p.id}>
								{p.name}
							</option>
						))}
					</select>
				</div>
			</div>

			{/* Monthly summary stats */}
			{monthSummary && monthSummary.totalMinutes > 0 && (
				<div className="space-y-2">
					<div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
						<SummaryCard
							label="Hours this month"
							value={formatDuration(monthSummary.totalMinutes)}
							accent
						/>
						<SummaryCard label="Sessions" value={String(monthSummary.totalSessions)} />
						<SummaryCard label="Active days" value={String(monthSummary.activeDays)} />
						<SummaryCard
							label="Daily average"
							value={formatDuration(monthSummary.avgDailyMinutes)}
						/>
					</div>
					<div className="flex justify-end">
						<Link
							to={`/insights/month/${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, "0")}`}
							className="text-xs text-accent hover:text-accent/80 transition-colors"
						>
							View full monthly retrospective &rarr;
						</Link>
					</div>
				</div>
			)}

			{/* Intelligence: Pattern cards */}
			{!selectedProjectId && !selectedTag && <PatternCards />}

			{/* Today's flow score + repo / language dimensions, from the daemon */}
			{!selectedProjectId && !selectedTag && (
				<>
					<FlowToday />
					<FlowThisWeek />
					<div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
						<FlowByRepo />
						<FlowByLanguage />
					</div>
				</>
			)}

			<ContributionHeatmap projectId={selectedProjectId} tag={selectedTag} />

			<div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
				<DailyRhythmChart projectId={selectedProjectId} tag={selectedTag} />
				{!selectedProjectId && <TopProjects tag={selectedTag} />}
			</div>

			{/* Intelligence: Mood, Health, Estimation */}
			{!selectedProjectId && !selectedTag && (
				<div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
					<MoodCorrelation />
					<ProjectHealth />
					<EstimationAccuracy />
				</div>
			)}

			{/* Weekly shareable card */}
			{!selectedProjectId && !selectedTag && <WeeklyCard />}
		</div>
	);
}

function SummaryCard({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
	return (
		<div className="rounded-lg border border-border/60 bg-secondary/20 px-4 py-3 text-center">
			<p className="text-muted-foreground text-[10px] uppercase tracking-[0.14em] mb-1">{label}</p>
			<p
				className={`font-heading text-lg font-semibold tabular-nums ${accent ? "text-accent" : "text-foreground"}`}
			>
				{value}
			</p>
		</div>
	);
}
