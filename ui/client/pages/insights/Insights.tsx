/**
 * Insights Page
 * Analytics dashboard with summary stats, contribution heatmap,
 * daily rhythm chart, and top projects breakdown.
 */
import { X } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router";
import { ProjectPicker, useProjects, visibleProjects } from "@/entities/project";
import { useAllTags, useHeatmap } from "@/entities/session";
import { formatDuration } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { BestMoment } from "./BestMoment";
import { ContributionHeatmap } from "./ContributionHeatmap";
import { DailyRhythmChart } from "./DailyRhythmChart";
import { DistractionsToday } from "./DistractionsToday";
import { FlowByApp } from "./FlowByApp";
import { FlowByLanguage } from "./FlowByLanguage";
import { FlowByRepo } from "./FlowByRepo";
import { FlowByWeekday } from "./FlowByWeekday";
import { FlowFilterChips } from "./FlowFilterChips";
import { FlowRhythm } from "./FlowRhythm";
import { FlowThisWeek } from "./FlowThisWeek";
import { FlowToday } from "./FlowToday";
import { FlowTrend } from "./FlowTrend";
import { PatternCards } from "./PatternCards";
import { ProjectHealth } from "./ProjectHealth";
import { LABEL, SKY_CHIP } from "./styles";
import { TopProjects } from "./TopProjects";
import { useInsightsFilters } from "./useInsightsFilters";
import { WeeklyCard } from "./WeeklyCard";

export default function Insights() {
	// Every filter on this page is URL-persisted so the whole view (project +
	// tag dropdowns + click-to-filter chips) is bookmarkable as one unit.
	// Refreshing or sharing the URL reproduces the exact slice the user was
	// looking at — the inconsistency of "chips persist but dropdowns reset"
	// would surprise anyone who actually tries it. The "clear all filters"
	// link only shows when 2+ are active; one filter is trivially clearable
	// via its own dropdown / dismiss pill.
	const {
		selectedProjectId,
		setSelectedProjectId,
		selectedTag,
		setSelectedTag,
		selectedRepo,
		setSelectedRepo,
		selectedLanguage,
		setSelectedLanguage,
		selectedBundleId,
		setSelectedBundleId,
		activeFilterCount,
		clearAllFilters,
	} = useInsightsFilters();
	const { data: projects } = useProjects();
	const { data: allTags } = useAllTags();
	const currentYear = new Date().getFullYear();
	const { data: heatmapData } = useHeatmap(currentYear, selectedProjectId, selectedTag);

	const activeProjects = visibleProjects(projects);

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
			<div className="flex flex-wrap items-center justify-between gap-y-2">
				<div className="flex flex-wrap items-center gap-3">
					<h1 className="font-heading text-xl text-foreground shrink-0">Insights</h1>
					<Link to="/insights/digests" className={SKY_CHIP}>
						Digests
					</Link>
					<Link to={`/insights/year/${new Date().getFullYear() - 1}`} className={SKY_CHIP}>
						{new Date().getFullYear() - 1} Review
					</Link>
					{activeFilterCount >= 2 && (
						<button
							type="button"
							onClick={clearAllFilters}
							className={SKY_CHIP}
							title="Clear every filter on this page (or press Esc)"
						>
							× clear all filters ({activeFilterCount})
						</button>
					)}
				</div>
				<div className="flex items-center gap-2">
					{allTags && allTags.length > 0 && (
						<select
							name="tag-filter"
							aria-label="Filter by tag"
							value={selectedTag ?? ""}
							onChange={(e) => setSelectedTag(e.target.value || undefined)}
							className="min-h-9 rounded-full bg-card pl-3 pr-2 text-sm text-foreground transition-colors hover:bg-card/70 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
						>
							<option value="">All Tags</option>
							{allTags.map((tag) => (
								<option key={tag} value={tag}>
									{tag}
								</option>
							))}
						</select>
					)}
					<div className="flex items-center gap-1.5">
						<div className="w-48">
							<ProjectPicker
								projects={activeProjects}
								value={selectedProjectId ?? null}
								onChange={(id) => setSelectedProjectId(id ?? undefined)}
								compact
								triggerPlaceholder="All projects"
								ariaLabel="Filter by project"
							/>
						</div>
						{selectedProjectId && (
							<button
								type="button"
								onClick={() => setSelectedProjectId(undefined)}
								aria-label="Clear project filter"
								title="Show all projects"
								className="grid place-items-center w-7 h-7 rounded-full bg-card text-foreground hover:text-accent-ink transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
							>
								<X className="w-3.5 h-3.5" />
							</button>
						)}
					</div>
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
							className={SKY_CHIP}
						>
							View full monthly retrospective &rarr;
						</Link>
					</div>
				</div>
			)}

			{/* Intelligence: Pattern cards */}
			{!selectedProjectId && !selectedTag && <PatternCards />}

			{/* Today's flow score + repo / language dimensions, from the daemon.
			    Tag filter still hides these — flow windows don't carry tags. */}
			{!selectedTag && (
				<>
					{(selectedRepo || selectedLanguage || selectedBundleId) && (
						<FlowFilterChips
							repo={selectedRepo}
							language={selectedLanguage}
							bundleId={selectedBundleId}
							onClearRepo={() => setSelectedRepo(undefined)}
							onClearLanguage={() => setSelectedLanguage(undefined)}
							onClearBundleId={() => setSelectedBundleId(undefined)}
						/>
					)}
					<FlowToday
						projectId={selectedProjectId}
						editorRepo={selectedRepo}
						editorLanguage={selectedLanguage}
						bundleId={selectedBundleId}
					/>
					{/* Drift events aren't scoped by project/repo/language/app, so only
					    show this when no flow-dimension filter is active — otherwise it
					    would read as filtered when it isn't. */}
					{!selectedProjectId && !selectedRepo && !selectedLanguage && !selectedBundleId && (
						<DistractionsToday />
					)}
					<BestMoment
						projectId={selectedProjectId}
						editorRepo={selectedRepo}
						editorLanguage={selectedLanguage}
						bundleId={selectedBundleId}
					/>
					<FlowThisWeek
						projectId={selectedProjectId}
						editorRepo={selectedRepo}
						editorLanguage={selectedLanguage}
						bundleId={selectedBundleId}
					/>
					<FlowTrend
						projectId={selectedProjectId}
						editorRepo={selectedRepo}
						editorLanguage={selectedLanguage}
						bundleId={selectedBundleId}
					/>
					<div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
						<FlowRhythm
							projectId={selectedProjectId}
							editorRepo={selectedRepo}
							editorLanguage={selectedLanguage}
							bundleId={selectedBundleId}
						/>
						<FlowByWeekday
							projectId={selectedProjectId}
							editorRepo={selectedRepo}
							editorLanguage={selectedLanguage}
							bundleId={selectedBundleId}
						/>
					</div>
					<div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
						<FlowByRepo
							projectId={selectedProjectId}
							editorLanguage={selectedLanguage}
							bundleId={selectedBundleId}
							selectedRepo={selectedRepo}
							onSelectRepo={setSelectedRepo}
						/>
						<FlowByLanguage
							projectId={selectedProjectId}
							editorRepo={selectedRepo}
							bundleId={selectedBundleId}
							selectedLanguage={selectedLanguage}
							onSelectLanguage={setSelectedLanguage}
						/>
						<FlowByApp
							projectId={selectedProjectId}
							editorRepo={selectedRepo}
							editorLanguage={selectedLanguage}
							selectedBundleId={selectedBundleId}
							onSelectBundleId={setSelectedBundleId}
						/>
					</div>
				</>
			)}

			<ContributionHeatmap projectId={selectedProjectId} tag={selectedTag} />

			<div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
				<DailyRhythmChart projectId={selectedProjectId} tag={selectedTag} />
				{!selectedProjectId && <TopProjects tag={selectedTag} />}
			</div>

			{/* Intelligence: Project Health */}
			{!selectedProjectId && !selectedTag && (
				<div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
					<ProjectHealth />
				</div>
			)}

			{/* Weekly shareable card */}
			{!selectedProjectId && !selectedTag && <WeeklyCard />}
		</div>
	);
}

function SummaryCard({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
	return (
		<Panel padding="px-4 py-3.5" className="text-center">
			<p className={`${LABEL} mb-1`}>{label}</p>
			<p
				className={`font-heading text-lg tabular-nums text-foreground ${accent ? "font-extrabold" : "font-bold"}`}
			>
				{value}
			</p>
		</Panel>
	);
}
