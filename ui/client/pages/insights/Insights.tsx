/**
 * Insights Page
 * Analytics dashboard, split into tabs (the UX-refresh mockup's pill
 * tablist): Overview (the at-a-glance read), Flow (the daemon's flow
 * charts), Where time goes (repo / language / app / project breakdowns)
 * and Reviews (digests and the month / year retrospectives).
 *
 * The project and tag filters sit above the tabs because they filter
 * every tab; the selected tab itself is URL-persisted (`?tab=`) like the
 * filters, so the whole view is bookmarkable as one unit. An unknown
 * `?tab=` value reads as "overview".
 */
import { X } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router";
import { ProjectPicker, useProjects, visibleProjects } from "@/entities/project";
import { useAllTags, useHeatmap } from "@/entities/session";
import { formatDuration, useUrlParam } from "@/shared/lib";
import { Panel, TabPanel, Tabs } from "@/shared/ui";
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

const INSIGHTS_TABS = [
	{ value: "overview", label: "Overview" },
	{ value: "flow", label: "Flow" },
	{ value: "time", label: "Where time goes" },
	{ value: "reviews", label: "Reviews" },
] as const;

export type InsightsTab = (typeof INSIGHTS_TABS)[number]["value"];

/** Read any `?tab=` value as a tab; anything unknown is "overview". */
export function resolveInsightsTab(raw: string | undefined): InsightsTab {
	const match = INSIGHTS_TABS.find((t) => t.value === raw);
	return match ? match.value : "overview";
}

export default function Insights() {
	// Every filter on this page is URL-persisted so the whole view (project +
	// tag dropdowns + click-to-filter chips + the selected tab) is bookmarkable
	// as one unit. Refreshing or sharing the URL reproduces the exact slice the
	// user was looking at — the inconsistency of "chips persist but dropdowns
	// reset" would surprise anyone who actually tries it. The "clear all
	// filters" link only shows when 2+ are active; one filter is trivially
	// clearable via its own dropdown / dismiss pill.
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
	const [rawTab, setRawTab] = useUrlParam("tab");
	const tab = resolveInsightsTab(rawTab);
	// The default tab keeps a clean URL: ?tab=overview and no ?tab= are the
	// same view, so we never write the default.
	const setTab = (next: InsightsTab) => setRawTab(next === "overview" ? undefined : next);
	const { data: projects } = useProjects();
	const { data: allTags } = useAllTags();
	const now = new Date();
	const currentYear = now.getFullYear();
	const currentMonth = `${currentYear}-${String(now.getMonth() + 1).padStart(2, "0")}`;
	const { data: heatmapData } = useHeatmap(currentYear, selectedProjectId, selectedTag);

	const activeProjects = visibleProjects(projects);

	// Compute current month summary from heatmap data
	const monthSummary = useMemo(() => {
		if (!heatmapData) return null;
		const today = new Date();
		const monthPrefix = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
		const monthDays = heatmapData.filter((d) => d.date.startsWith(monthPrefix));

		const totalMinutes = monthDays.reduce((sum, d) => sum + d.total_minutes, 0);
		const totalSessions = monthDays.reduce((sum, d) => sum + d.session_count, 0);
		const activeDays = monthDays.filter((d) => d.total_minutes > 0).length;
		const daysElapsed = today.getDate();
		const avgDailyMinutes = daysElapsed > 0 ? totalMinutes / daysElapsed : 0;

		return { totalMinutes, totalSessions, activeDays, avgDailyMinutes };
	}, [heatmapData]);

	// Flow charts read the daemon's flow windows, which don't carry tags, so a
	// tag filter hides them rather than pretending to apply.
	const flowHidden = Boolean(selectedTag);
	const flowDimensionFilterActive = Boolean(selectedRepo || selectedLanguage || selectedBundleId);

	return (
		<div className="max-w-5xl mx-auto px-6 py-6 space-y-5">
			{/* Header with the filters that apply to every tab */}
			<div className="flex flex-wrap items-center justify-between gap-y-2">
				<div className="flex flex-wrap items-center gap-3">
					<h1 className="font-heading text-xl text-foreground shrink-0">Insights</h1>
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

			<Tabs tabs={INSIGHTS_TABS} value={tab} onChange={setTab} label="Insights sections" />

			{/* Flow-dimension chips filter flow charts on every tab but Reviews,
			    so they sit above the panels rather than inside one of them. */}
			{!flowHidden && flowDimensionFilterActive && tab !== "reviews" && (
				<FlowFilterChips
					repo={selectedRepo}
					language={selectedLanguage}
					bundleId={selectedBundleId}
					onClearRepo={() => setSelectedRepo(undefined)}
					onClearLanguage={() => setSelectedLanguage(undefined)}
					onClearBundleId={() => setSelectedBundleId(undefined)}
				/>
			)}

			<TabPanel value="overview" current={tab} className="space-y-5">
				{/* Monthly summary stats */}
				{monthSummary && monthSummary.totalMinutes > 0 && (
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
				)}

				{/* Intelligence: Pattern cards */}
				{!selectedProjectId && !selectedTag && <PatternCards />}

				{/* Today's flow score and its best moment, from the daemon */}
				{!flowHidden && (
					<>
						<FlowToday
							projectId={selectedProjectId}
							editorRepo={selectedRepo}
							editorLanguage={selectedLanguage}
							bundleId={selectedBundleId}
						/>
						<BestMoment
							projectId={selectedProjectId}
							editorRepo={selectedRepo}
							editorLanguage={selectedLanguage}
							bundleId={selectedBundleId}
						/>
					</>
				)}

				<ContributionHeatmap projectId={selectedProjectId} tag={selectedTag} />

				{/* Weekly shareable card */}
				{!selectedProjectId && !selectedTag && <WeeklyCard />}
			</TabPanel>

			<TabPanel value="flow" current={tab} className="space-y-5">
				{/* Flow windows don't carry tags, so the tag filter hides them. */}
				{!flowHidden && (
					<>
						{/* Drift events aren't scoped by project/repo/language/app, so only
						    show this when no flow-dimension filter is active — otherwise it
						    would read as filtered when it isn't. */}
						{!selectedProjectId && !flowDimensionFilterActive && <DistractionsToday />}
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
					</>
				)}
				<DailyRhythmChart projectId={selectedProjectId} tag={selectedTag} />
			</TabPanel>

			<TabPanel value="time" current={tab} className="space-y-5">
				{!flowHidden && (
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
				)}

				{!selectedProjectId && (
					<div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
						<TopProjects tag={selectedTag} />
					</div>
				)}

				{/* Intelligence: Project Health */}
				{!selectedProjectId && !selectedTag && (
					<div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
						<ProjectHealth />
					</div>
				)}
			</TabPanel>

			<TabPanel value="reviews" current={tab}>
				<Panel className="space-y-4">
					<div>
						<h2 className="font-heading text-base font-bold text-foreground">Reviews</h2>
						<p className="text-sm text-muted-foreground">
							Longer looks back: weekly digests and the month and year retrospectives.
						</p>
					</div>
					<ul className="space-y-2">
						<li>
							<Link to="/insights/digests" className={SKY_CHIP}>
								Weekly digests
							</Link>
						</li>
						<li>
							<Link to={`/insights/month/${currentMonth}`} className={SKY_CHIP}>
								This month's retrospective
							</Link>
						</li>
						<li>
							<Link to={`/insights/year/${currentYear}`} className={SKY_CHIP}>
								{currentYear} Review
							</Link>
						</li>
						<li>
							<Link to={`/insights/year/${currentYear - 1}`} className={SKY_CHIP}>
								{currentYear - 1} Review
							</Link>
						</li>
					</ul>
				</Panel>
			</TabPanel>
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
