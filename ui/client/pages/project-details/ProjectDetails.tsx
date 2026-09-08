/**
 * Project Details Page
 * Compact header, week history table, and paginated session list.
 */

import { ChevronLeft, Clock, Settings } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { useProjectGitActivityByWeek } from "@/entities/github";
import { useProjectPlannedByWeek } from "@/entities/planning";
import {
	LoadingSpinner,
	useProject,
	useProjects,
	useProjectWeeks,
	useUpdateProject,
} from "@/entities/project";
import {
	calculateDailySummary,
	useDeleteSession,
	useSessions,
	useUpdateSession,
} from "@/entities/session";
import { describeError } from "@/shared/api";
import { getWeekNumberLabel, parseTimedeltaToMinutes, parseUtcIso, startOfDay } from "@/shared/lib";
import { ColorPicker, GoalRing } from "@/shared/ui";
import { ProjectDangerZone } from "./ProjectDangerZone";
import { ProjectGitHubBadge } from "./ProjectGitHubBadge";
import { ProjectHealthRail } from "./ProjectHealthRail";
import { ProjectSessionList } from "./ProjectSessionList";
import { ProjectSettingsDrawer } from "./ProjectSettingsDrawer";
import { ProjectStats } from "./ProjectStats";
import { ProjectWeekHistory } from "./ProjectWeekHistory";
import { computeMondayIsoList } from "./weekIso";

const WEEKDAYS = [
	"Monday",
	"Tuesday",
	"Wednesday",
	"Thursday",
	"Friday",
	"Saturday",
	"Sunday",
] as const;

export default function ProjectDetails() {
	const { projectId } = useParams<{ projectId: string }>();
	const [weekCount, setWeekCount] = useState(5);
	const [colorPickerOpen, setColorPickerOpen] = useState(false);
	const [settingsOpen, setSettingsOpen] = useState(false);
	const [settingsFocus, setSettingsFocus] = useState<
		"name" | "description" | "weeklyGoal" | "githubRepo"
	>("name");
	const navigate = useNavigate();
	// P4.0: click a week label in the history table to scope the sessions
	// list below to that week's Mon..Sun range. null = no scope.
	const [scopedWeeksAgo, setScopedWeeksAgo] = useState<number | null>(null);
	const hasSetInitialExpand = useRef(false);

	const openSettings = (field: "name" | "description" | "weeklyGoal" | "githubRepo") => {
		setSettingsFocus(field);
		setSettingsOpen(true);
	};

	const { data: project, isLoading: projectLoading, error: projectError } = useProject(projectId);
	const { data: allProjects } = useProjects();
	const { data: sessions, refetch: refetchSessions } = useSessions(projectId);
	const { data: hoursPerWeek } = useProjectWeeks(projectId, weekCount);
	const updateSessionMutation = useUpdateSession();
	const deleteSessionMutation = useDeleteSession();
	const updateProjectMutation = useUpdateProject();

	// P4.1: planned hours per week for this project. Hook must sit above the
	// loading/not-found early return; Monday list is derived from weekCount
	// rather than from project so the call stays unconditional. Undefined
	// for a row = "no plan entry that week" (em-dash); 0 = explicit zero.
	const mondayIsoList = computeMondayIsoList(weekCount);
	const { byMondayIso: plannedByMonday } = useProjectPlannedByWeek(projectId, mondayIsoList);
	// P4.4: weekly commit counts for the project's linked GitHub repo. Empty
	// map when the repo isn't set or the user isn't OAuth-connected — the
	// table renders an em-dash with a tooltip explaining the precondition.
	const { byMondayIso: commitsByMonday } = useProjectGitActivityByWeek(projectId, mondayIsoList);

	// Reset per-project view state when the route project changes. projectId is
	// the intentional trigger here (the body only calls stable setters), so it
	// belongs in the deps even though Biome can't infer that it's read.
	// biome-ignore lint/correctness/useExhaustiveDependencies: projectId is the reset trigger, not a body dependency
	useEffect(() => {
		setWeekCount(5);
		hasSetInitialExpand.current = false;
	}, [projectId]);

	const handleSaveEdit = async (
		sessionId: string,
		startTime: string,
		endTime: string,
		projectIdForSession: string,
	) => {
		const session = sessions?.find((s) => s.id === sessionId);
		if (!session) return;

		try {
			await updateSessionMutation.mutateAsync({
				session,
				startTime,
				endTime,
				projectId: projectIdForSession,
			});
			toast.success("Session updated");
			refetchSessions();
		} catch {
			toast.error("Failed to update session");
		}
	};

	const handleDeleteSession = async (sessionId: string) => {
		try {
			await deleteSessionMutation.mutateAsync(sessionId);
			toast.success("Session deleted");
			refetchSessions();
		} catch (err) {
			toast.error(describeError(err, "Failed to delete session"));
		}
	};

	if (projectLoading) {
		return <LoadingSpinner message="Loading project..." />;
	}

	if (projectError || !project) {
		return (
			<div className="max-w-3xl mx-auto px-6 py-12">
				<div className="text-center py-20">
					<Clock className="w-10 h-10 text-muted-foreground/30 mx-auto mb-3" />
					<p className="text-muted-foreground text-sm">Project not found</p>
				</div>
			</div>
		);
	}

	const sessionList = sessions || [];
	const weekList = hoursPerWeek || [];
	const dailySummary = calculateDailySummary(sessionList);
	const totalMinutes = project.totalMinutes || 0;
	const totalHours = totalMinutes > 0 ? (totalMinutes / 60).toFixed(1) : "0";
	const weeklyHours = project.weeklyMinutes ? project.weeklyMinutes / 60 : 0;
	// effectiveGoal === null means an override explicitly set "no goal" for
	// this week — don't fall back to project.weeklyGoal in that case.
	const headerGoal = project.effectiveGoalOverridden
		? (project.effectiveGoal ?? null)
		: (project.effectiveGoal ?? project.weeklyGoal ?? null);
	const headerGoalType = project.effectiveGoalType ?? project.goalType ?? "target";
	const goalPct = headerGoal ? Math.min((weeklyHours / headerGoal) * 100, 100) : null;

	const sortedSessions = [...sessionList].sort(
		(a, b) => parseUtcIso(b.startTime).getTime() - parseUtcIso(a.startTime).getTime(),
	);

	// Build week history rows: current week + past weeks
	const today = startOfDay();
	const todayDayIndex = (today.getDay() + 6) % 7; // Monday=0 ... Sunday=6

	// Helper: get the Monday ISO string for a given weeksAgo
	const getMondayIso = (weeksAgo: number): string => {
		const d = new Date();
		d.setHours(12, 0, 0, 0); // noon to avoid DST/UTC edge cases
		d.setDate(d.getDate() - ((d.getDay() + 6) % 7) - weeksAgo * 7);
		const yyyy = d.getFullYear();
		const mm = String(d.getMonth() + 1).padStart(2, "0");
		const dd = String(d.getDate()).padStart(2, "0");
		return `${yyyy}-${mm}-${dd}`;
	};

	// Week-0 data drives the current-week goal. The server already resolves the
	// project default into effective_goal, so a null value always means "no
	// goal" — no client-side fallback needed.
	const week0Data = weekList.find((w) => w.weeksAgo === 0);

	const currentWeekRow = {
		label: "This wk",
		weeksAgo: 0,
		mondayIso: week0Data?.weekStart ?? getMondayIso(0),
		days: WEEKDAYS.map((dayName) => {
			const day = dailySummary.find((d) => d.dayName === dayName);
			return day?.totalMinutes ?? 0;
		}),
		total: dailySummary.reduce((sum, d) => sum + d.totalMinutes, 0),
		effectiveGoal: week0Data ? (week0Data.effectiveGoal ?? null) : headerGoal,
		effectiveGoalType: (week0Data?.effectiveGoalType ?? headerGoalType) as "target" | "cap",
		effectiveGoalOverridden: week0Data?.effectiveGoalOverridden ?? false,
	};

	const pastWeekRows = weekList
		.filter((w) => w.weeksAgo > 0)
		.map((week) => ({
			label: getWeekNumberLabel(week.weeksAgo),
			weeksAgo: week.weeksAgo,
			// Key off the server's canonical Monday so the override we save lines
			// up with the week the server resolves it against.
			mondayIso: week.weekStart ?? getMondayIso(week.weeksAgo),
			days: WEEKDAYS.map((dayName) =>
				parseTimedeltaToMinutes(week.dailyDurations[dayName] || "0:00:00"),
			),
			total: week.hours * 60,
			// effective_goal is fully resolved server-side (override → permanent →
			// project default), so null always means "no goal".
			effectiveGoal: week.effectiveGoal ?? null,
			effectiveGoalType: (week.effectiveGoalType ?? project.goalType ?? "target") as
				| "target"
				| "cap",
			effectiveGoalOverridden: week.effectiveGoalOverridden ?? false,
		}));

	const allWeekRows = [currentWeekRow, ...pastWeekRows];
	const hasAnyGoal =
		project.weeklyGoal != null ||
		(project.goalOverrides || []).length > 0 ||
		allWeekRows.some((r) => r.effectiveGoal != null);

	// Save/remove goal override handlers

	return (
		<div>
			{/* Mobile back-link breadcrumb (P0 a11y principle). Hidden on >= lg
			    because the sidebar is the nav surface there. */}
			<Link
				to="/app"
				className="lg:hidden inline-flex items-center gap-1 text-xs text-muted-foreground px-6 pt-3 hover:text-foreground transition-colors"
			>
				<ChevronLeft className="w-3.5 h-3.5" />
				Back
			</Link>

			{/* Compact header */}
			<header className="border-b border-border/50">
				<div className="max-w-5xl mx-auto px-6 py-3 flex items-center gap-3">
					<div className="relative">
						<button
							type="button"
							onClick={() => setColorPickerOpen((o) => !o)}
							className="w-3 h-3 rounded-full shrink-0 hover:ring-2 hover:ring-accent/40 transition-all cursor-pointer"
							style={{
								backgroundColor: project.color || "hsl(var(--muted-foreground))",
							}}
							title="Change color"
						/>
						{colorPickerOpen && (
							<ColorPicker
								value={project.color || "#FBBF24"}
								onChange={(color) => {
									updateProjectMutation.mutate({
										id: project.id,
										name: project.name,
										description: project.description,
										color,
										archived: project.archived,
										weekly_goal: project.weeklyGoal,
										goal_type: project.goalType,
									});
								}}
								onClose={() => setColorPickerOpen(false)}
							/>
						)}
					</div>
					{/* Inline-clickable title: opens the settings drawer focused on
					    name. Replaces the read-only h1 — the color dot was the only
					    edit affordance pre-P1.2a. */}
					<button
						type="button"
						onClick={() => openSettings("name")}
						className="font-heading text-xl text-foreground truncate text-left hover:text-accent transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 rounded"
						title="Edit project"
					>
						{project.name}
					</button>
					{project.archived && (
						<span
							className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border border-muted-foreground/40 text-muted-foreground shrink-0"
							title="This project is archived. Hidden from active pickers and lists."
						>
							Archived
						</span>
					)}
					{project.description ? (
						<button
							type="button"
							onClick={() => openSettings("description")}
							className="text-muted-foreground text-sm hidden md:inline truncate max-w-[200px] text-left hover:text-foreground transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 rounded"
							title="Edit description"
						>
							— {project.description}
						</button>
					) : (
						<button
							type="button"
							onClick={() => openSettings("description")}
							className="text-muted-foreground/50 text-sm hidden md:inline hover:text-muted-foreground transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 rounded"
						>
							+ Add description
						</button>
					)}
					<ProjectGitHubBadge
						githubRepo={project.githubRepo}
						onConfigureRepo={() => openSettings("githubRepo")}
						onConnectGitHub={() => navigate("/settings#github")}
					/>
					<div className="ml-auto shrink-0 flex items-center gap-4">
						{goalPct !== null ? (
							<button
								type="button"
								onClick={() => openSettings("weeklyGoal")}
								title="Edit weekly goal"
								className="hidden sm:flex items-center gap-2 rounded-md px-1 py-0.5 hover:bg-secondary/40 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
							>
								<GoalRing
									percent={goalPct}
									size={28}
									strokeWidth={3}
									isCap={headerGoalType === "cap"}
								/>
								<span className="text-xs tabular-nums text-muted-foreground">
									{weeklyHours.toFixed(1)}/{headerGoal}h
								</span>
							</button>
						) : (
							<button
								type="button"
								onClick={() => openSettings("weeklyGoal")}
								className="hidden sm:inline-flex items-center gap-1 text-xs text-muted-foreground/60 hover:text-accent transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 rounded"
							>
								+ Set weekly goal
							</button>
						)}
						<span className="font-heading text-lg font-semibold tabular-nums text-accent">
							{totalHours}h
						</span>
						<button
							type="button"
							onClick={() => openSettings("name")}
							aria-label="Project settings"
							title="Project settings"
							className="p-2 -m-1 rounded-md text-muted-foreground/60 hover:text-foreground hover:bg-secondary/50 transition focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
						>
							<Settings className="w-4 h-4" />
						</button>
					</div>
				</div>
			</header>

			<main className="max-w-5xl mx-auto px-6 pb-24">
				{/* Project Health rail (P4.3) — alerts + recency + goal trend +
				    today's average focus. */}
				<ProjectHealthRail
					projectId={project.id}
					todaysProjectSessions={sessionList.filter(
						(s) => parseUtcIso(s.startTime) >= startOfDay(),
					)}
				/>

				{/* Stats above the fold (P4.0) — lead the page with project shape,
				    not the session list. */}
				<ProjectStats sessions={sessionList} lastTrackedAt={project.lastTrackedAt} />

				<ProjectWeekHistory
					rows={allWeekRows}
					hasAnyGoal={hasAnyGoal}
					todayDayIndex={todayDayIndex}
					plannedByMonday={plannedByMonday}
					commitsByMonday={commitsByMonday}
					hasGitHubRepo={Boolean(project.githubRepo)}
					projectId={project.id}
					weeklyGoal={project.weeklyGoal}
					goalOverrides={project.goalOverrides || []}
					scopedWeeksAgo={scopedWeeksAgo}
					onScopeWeek={setScopedWeeksAgo}
					onShowMoreWeeks={() => setWeekCount((c) => c + 5)}
				/>

				<ProjectSessionList
					// Keyed so navigating to another project remounts the list and
					// resets its pagination, which the page used to do by hand.
					key={projectId}
					sessions={sortedSessions}
					allProjects={allProjects || []}
					scopedWeeksAgo={scopedWeeksAgo}
					scopeLabel={allWeekRows.find((r) => r.weeksAgo === scopedWeeksAgo)?.label ?? "week"}
					onClearScope={() => setScopedWeeksAgo(null)}
					onSave={handleSaveEdit}
					onDelete={handleDeleteSession}
					isDeleting={deleteSessionMutation.isPending}
				/>

				<ProjectDangerZone
					projectId={project.id}
					projectName={project.name}
					archived={project.archived}
				/>
			</main>

			<ProjectSettingsDrawer
				project={project}
				open={settingsOpen}
				onClose={() => setSettingsOpen(false)}
				autoFocusField={settingsFocus}
			/>
		</div>
	);
}

/**
 * One cell in the week-history table's "Planned" column.
 * - undefined  → em-dash (no plan entry for this project that week)
 * - 0          → "0h"     (plan explicitly set this project to zero)
 * - n          → "n.nh"
 */

/**
 * Commits cell for the week-history table (P4.4).
 *
 * - `hasRepo === false` → em-dash with a tooltip pointing at the linked-repo
 *   precondition. Same em-dash as "no plan" so the column doesn't shout an
 *   empty state at a user who hasn't opted into the integration.
 * - `hasRepo === true` and count is undefined/0 → "0" in muted color.
 * - `hasRepo === true` and count > 0 → the count, with a tooltip.
 *
 * The Map from useProjectGitActivityByWeek seeds every visible Monday with 0
 * up-front, so an empty repo period reads "0" rather than the no-repo "—".
 */
