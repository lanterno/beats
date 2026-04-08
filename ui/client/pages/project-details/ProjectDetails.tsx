/**
 * Project Details Page
 * Compact header, week history table, and paginated session list.
 */

import { Clock, Edit2, List } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import {
	LoadingSpinner,
	useProject,
	useProjects,
	useProjectWeeks,
	useUpdateProject,
} from "@/entities/project";
import type { Session } from "@/entities/session";
import {
	calculateDailySummary,
	SessionEditForm,
	useSessions,
	useUpdateSession,
} from "@/entities/session";
import {
	formatDate,
	formatDuration,
	formatTime,
	getWeekNumberLabel,
	parseTimedeltaToMinutes,
	parseUtcIso,
} from "@/shared/lib";
import { ColorPicker, EmptyState, GoalRing } from "@/shared/ui";
import { SessionTimeline } from "./SessionTimeline";

const SESSIONS_PER_PAGE = 20;
const WEEKDAYS = [
	"Monday",
	"Tuesday",
	"Wednesday",
	"Thursday",
	"Friday",
	"Saturday",
	"Sunday",
] as const;
const WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

export default function ProjectDetails() {
	const { projectId } = useParams<{ projectId: string }>();
	const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
	const [visibleCount, setVisibleCount] = useState(SESSIONS_PER_PAGE);
	const [weekCount, setWeekCount] = useState(5);
	const [colorPickerOpen, setColorPickerOpen] = useState(false);
	const hasSetInitialExpand = useRef(false);

	const { data: project, isLoading: projectLoading, error: projectError } = useProject(projectId);
	const { data: allProjects } = useProjects();
	const { data: sessions, refetch: refetchSessions } = useSessions(projectId);
	const { data: hoursPerWeek } = useProjectWeeks(projectId, weekCount);
	const updateSessionMutation = useUpdateSession();
	const updateProjectMutation = useUpdateProject();

	// Reset visible count when project changes
	useEffect(() => {
		setVisibleCount(SESSIONS_PER_PAGE);
		setWeekCount(5);
		hasSetInitialExpand.current = false;
	}, []);

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
			setEditingSessionId(null);
			toast.success("Session updated");
			refetchSessions();
		} catch {
			toast.error("Failed to update session");
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
	const goalPct = project.weeklyGoal
		? Math.min((weeklyHours / project.weeklyGoal) * 100, 100)
		: null;

	const sortedSessions = [...sessionList].sort(
		(a, b) => parseUtcIso(b.startTime).getTime() - parseUtcIso(a.startTime).getTime(),
	);

	const visibleSessions = sortedSessions.slice(0, visibleCount);
	const hasMore = visibleCount < sortedSessions.length;

	// Group visible sessions by date
	const sessionsByDate = visibleSessions.reduce(
		(acc, session) => {
			const date = formatDate(session.startTime);
			if (!acc[date]) acc[date] = [];
			acc[date].push(session);
			return acc;
		},
		{} as Record<string, Session[]>,
	);

	// Build week history rows: current week + past weeks
	const today = new Date();
	today.setHours(0, 0, 0, 0);
	const todayDayIndex = (today.getDay() + 6) % 7; // Monday=0 ... Sunday=6

	const currentWeekRow = {
		label: "This wk",
		days: WEEKDAYS.map((dayName) => {
			const day = dailySummary.find((d) => d.dayName === dayName);
			return day?.totalMinutes ?? 0;
		}),
		total: dailySummary.reduce((sum, d) => sum + d.totalMinutes, 0),
	};

	const pastWeekRows = weekList
		.filter((w) => w.weeksAgo > 0)
		.map((week) => ({
			label: getWeekNumberLabel(week.weeksAgo),
			days: WEEKDAYS.map((dayName) =>
				parseTimedeltaToMinutes(week.dailyDurations[dayName] || "0:00:00"),
			),
			total: week.hours * 60,
		}));

	const allWeekRows = [currentWeekRow, ...pastWeekRows];

	return (
		<div>
			{/* Compact header */}
			<header className="border-b border-border/50">
				<div className="max-w-5xl mx-auto px-6 py-3 flex items-center gap-3">
					<div className="relative">
						<button
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
					<h1 className="font-heading text-xl text-foreground truncate">{project.name}</h1>
					{project.description && (
						<span className="text-muted-foreground text-sm hidden md:inline truncate max-w-[200px]">
							— {project.description}
						</span>
					)}
					<div className="ml-auto shrink-0 flex items-center gap-4">
						{goalPct !== null && (
							<div className="hidden sm:flex items-center gap-2">
								<GoalRing
									percent={goalPct}
									size={28}
									strokeWidth={3}
									isCap={project.goalType === "cap"}
								/>
								<span className="text-xs tabular-nums text-muted-foreground">
									{weeklyHours.toFixed(1)}/{project.weeklyGoal}h
								</span>
							</div>
						)}
						<span className="font-heading text-lg font-semibold tabular-nums text-accent">
							{totalHours}h
						</span>
					</div>
				</div>
			</header>

			<main className="max-w-5xl mx-auto px-6 pb-24">
				{/* Session Stats */}
				{sessionList.length > 0 && <SessionStatsBar sessions={sessionList} />}

				{/* Session Timeline */}
				{sessionList.length > 0 && (
					<SessionTimeline sessions={sessionList} projectColor={project.color || "#d4952a"} />
				)}

				{/* Week History Table */}
				<section className="mt-6" aria-label="Week history">
					<div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden">
						{/* Header */}
						<div className="grid grid-cols-[72px_repeat(7,1fr)_64px] px-3 py-2 border-b border-border/60">
							<div />
							{WEEKDAY_SHORT.map((d, i) => (
								<div
									key={d}
									className={`text-center text-[10px] uppercase tracking-widest ${
										i === todayDayIndex ? "text-accent font-semibold" : "text-muted-foreground"
									}`}
								>
									{d}
								</div>
							))}
							<div className="text-right text-[10px] uppercase tracking-widest text-muted-foreground">
								Total
							</div>
						</div>

						{/* Week rows */}
						{allWeekRows.map((row, rowIdx) => (
							<div
								key={row.label}
								className={`grid grid-cols-[72px_repeat(7,1fr)_64px] px-3 py-1.5 border-b border-border/20 last:border-b-0 ${
									rowIdx === 0 ? "bg-secondary/10" : "hover:bg-secondary/10"
								}`}
							>
								<div className="text-xs text-muted-foreground truncate pr-1">{row.label}</div>
								{row.days.map((mins, i) => (
									<div
										key={i}
										className={`text-center text-xs tabular-nums ${
											mins > 0
												? rowIdx === 0 && i === todayDayIndex
													? "text-accent font-medium"
													: "text-foreground"
												: "text-muted-foreground/30"
										}`}
									>
										{mins > 0 ? `${(mins / 60).toFixed(1)}` : "—"}
									</div>
								))}
								<div className="text-right text-sm font-medium tabular-nums text-accent">
									{row.total > 0 ? `${(row.total / 60).toFixed(1)}h` : "—"}
								</div>
							</div>
						))}

						{/* Show more weeks */}
						<button
							onClick={() => setWeekCount((c) => c + 5)}
							className="w-full py-2 text-sm text-accent hover:bg-accent/5 transition-colors border-t border-border/40"
						>
							Show 5 more weeks...
						</button>
					</div>
				</section>

				{/* Sessions */}
				<section className="mt-6" aria-labelledby="sessions-heading">
					<h2
						id="sessions-heading"
						className="flex items-center gap-2 text-foreground font-medium text-sm mb-3"
					>
						<List className="w-3.5 h-3.5 text-accent/75" />
						Sessions
						{sessionList.length > 0 && (
							<span className="text-xs text-muted-foreground font-normal">
								({sessionList.length})
							</span>
						)}
					</h2>

					{Object.entries(sessionsByDate).length === 0 ? (
						<div className="rounded-lg border border-dashed border-border">
							<EmptyState
								variant="clock"
								message="No sessions yet. Start the timer to begin tracking."
							/>
						</div>
					) : (
						<div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden">
							<div className="py-1">
								{Object.entries(sessionsByDate).map(([date, dateSessions]) => {
									const dayTotalMinutes = dateSessions.reduce(
										(sum, s) => sum + (s.duration || 0),
										0,
									);
									return (
										<div key={date}>
											{/* Date separator */}
											<div className="px-3 py-1 mt-2 first:mt-0">
												<span className="text-[10px] uppercase tracking-widest text-muted-foreground">
													{date}
												</span>
												<span className="text-[10px] text-muted-foreground/60 ml-1.5">
													— {dateSessions.length} session
													{dateSessions.length !== 1 ? "s" : ""}
													{dayTotalMinutes > 0 && (
														<span className="tabular-nums">
															, {formatDuration(dayTotalMinutes)}
														</span>
													)}
												</span>
											</div>

											{/* Session rows */}
											{dateSessions.map((session) => (
												<div key={session.id}>
													{editingSessionId === session.id ? (
														<div className="px-2 py-1">
															<SessionEditForm
																session={session}
																projects={(allProjects || []).map((p) => ({
																	id: p.id,
																	name: p.name,
																}))}
																onSave={handleSaveEdit}
																onCancel={() => setEditingSessionId(null)}
															/>
														</div>
													) : (
														<div className="px-3 py-1.5 hover:bg-secondary/30 transition-colors group">
															<div className="flex items-center gap-3">
																<span className="text-sm tabular-nums text-foreground">
																	{formatTime(session.startTime)} → {formatTime(session.endTime)}
																</span>
																<span
																	className={`text-sm font-medium tabular-nums ml-auto ${
																		session.duration > 0
																			? "text-accent"
																			: "text-muted-foreground/60"
																	}`}
																>
																	{session.duration > 0 ? formatDuration(session.duration) : "—"}
																</span>
																<button
																	onClick={() => setEditingSessionId(session.id)}
																	className="p-1 rounded text-muted-foreground/40 opacity-0 group-hover:opacity-100 hover:text-accent transition-all"
																	aria-label="Edit session"
																>
																	<Edit2 className="w-3.5 h-3.5" />
																</button>
															</div>
															{(session.note || session.tags.length > 0) && (
																<div className="flex items-center gap-1.5 mt-0.5">
																	{session.note && (
																		<span className="text-[11px] text-muted-foreground/60 truncate">
																			{session.note}
																		</span>
																	)}
																	{session.tags.map((tag) => (
																		<span
																			key={tag}
																			className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent/10 text-accent/70"
																		>
																			{tag}
																		</span>
																	))}
																</div>
															)}
														</div>
													)}
												</div>
											))}
										</div>
									);
								})}
							</div>

							{/* Load more */}
							{hasMore && (
								<div className="border-t border-border/40">
									<button
										onClick={() => setVisibleCount((c) => c + SESSIONS_PER_PAGE)}
										className="w-full py-2.5 text-sm text-accent hover:bg-accent/5 transition-colors"
									>
										Show {Math.min(SESSIONS_PER_PAGE, sortedSessions.length - visibleCount)} more
										sessions...
									</button>
								</div>
							)}
						</div>
					)}
				</section>
			</main>
		</div>
	);
}

function SessionStatsBar({ sessions }: { sessions: Session[] }) {
	const completed = sessions.filter((s) => s.duration > 0);
	if (completed.length === 0) return null;

	const totalDuration = completed.reduce((sum, s) => sum + s.duration, 0);
	const avgMinutes = totalDuration / completed.length;
	const longestMinutes = Math.max(...completed.map((s) => s.duration));

	const now = new Date();
	const thisMonthCount = completed.filter((s) => {
		const d = parseUtcIso(s.startTime);
		return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
	}).length;

	return (
		<div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-2">
			<StatCard label="Avg session" value={formatDuration(avgMinutes)} />
			<StatCard label="Longest" value={formatDuration(longestMinutes)} />
			<StatCard label="This month" value={`${thisMonthCount}`} sub="sessions" />
			<StatCard label="Total" value={`${completed.length}`} sub="sessions" />
		</div>
	);
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
	return (
		<div className="rounded-md border border-border/60 bg-secondary/20 px-3 py-2 text-center">
			<p className="text-muted-foreground text-[10px] uppercase tracking-[0.12em] mb-0.5">
				{label}
			</p>
			<p className="text-sm font-medium tabular-nums text-foreground">{value}</p>
			{sub && <p className="text-[10px] text-muted-foreground">{sub}</p>}
		</div>
	);
}
