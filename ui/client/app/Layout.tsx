/**
 * Layout Component
 * Sidebar-based shell with persistent timer for all authenticated pages.
 * Desktop: fixed left sidebar (w-64) + offset main content.
 * Mobile: sticky header with hamburger drawer.
 * Handles favicon indicator, keyboard shortcuts, command palette, and focus mode.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import {
	applyRecurringIntentions,
	useDailyNote,
	useIntentions,
	useUpsertDailyNote,
} from "@/entities/planning";
import { useProjects } from "@/entities/project";
import { useThisWeekSessions, useTodaySessions } from "@/entities/session";
import { useTimer } from "@/features/timer";
import {
	parseUtcIso,
	useCommandActions,
	useFavicon,
	useKeyboardShortcuts,
	useSyncEngine,
	useTheme,
	useTimerNotification,
} from "@/shared/lib";
import {
	CommandPalette,
	EndOfDayReview,
	FocusMode,
	MorningBriefing,
	WeeklyReviewDialog,
} from "@/shared/ui";
import { MobileHeader, Sidebar } from "@/widgets/sidebar";

export function Layout() {
	const { data: projects } = useProjects();
	const timer = useTimer();
	const location = useLocation();
	const { data: todaySessions } = useTodaySessions();
	const { data: weekSessions } = useThisWeekSessions();
	const { data: dailyNote } = useDailyNote();
	const upsertNote = useUpsertDailyNote();
	const { data: todayIntentions } = useIntentions();
	const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
	const [focusModeOpen, setFocusModeOpen] = useState(false);

	// Initialize theme + density from localStorage
	useTheme();

	// Start the offline mutation sync engine exactly once.
	useSyncEngine();

	// Apply recurring intentions on first load each day
	useEffect(() => {
		const key = "beats_recurring_applied";
		const today = new Date().toISOString().slice(0, 10);
		if (localStorage.getItem(key) !== today) {
			applyRecurringIntentions()
				.then(() => localStorage.setItem(key, today))
				.catch(() => {});
		}
	}, []);

	const projectsList = projects || [];
	const activeProjects = projectsList.filter((p) => !p.archived);
	const selectedProject = projectsList.find((p) => p.id === timer.selectedProjectId);

	// Today's summary for end-of-day review
	const todayTotalMinutes = (todaySessions ?? []).reduce((sum, s) => sum + (s.duration || 0), 0);
	const todaySessionCount = (todaySessions ?? []).length;
	const topProject = useMemo(() => {
		const byProject: Record<string, number> = {};
		for (const s of todaySessions ?? []) {
			if (s.projectId) byProject[s.projectId] = (byProject[s.projectId] ?? 0) + (s.duration || 0);
		}
		const topId = Object.entries(byProject).sort((a, b) => b[1] - a[1])[0]?.[0];
		return topId ? projectsList.find((p) => p.id === topId)?.name : undefined;
	}, [todaySessions, projectsList]);

	// Compute total seconds (handles custom start time)
	let totalSeconds = timer.elapsedSeconds;
	if (timer.customStartTime && timer.isRunning) {
		const startDate = parseUtcIso(timer.customStartTime);
		const now = new Date();
		totalSeconds = Math.floor((now.getTime() - startDate.getTime()) / 1000);
	}

	useFavicon(timer.isRunning, selectedProject?.color);
	useTimerNotification(timer.isRunning, timer.elapsedSeconds, selectedProject?.name);

	const toggleTimer = useCallback(() => {
		if (timer.isRunning) {
			timer.stopTimer();
		} else if (timer.selectedProjectId) {
			timer.startTimer(timer.selectedProjectId);
		}
	}, [timer]);

	const selectProjectByIndex = useCallback(
		(index: number) => {
			if (index < activeProjects.length) {
				timer.selectProject(activeProjects[index].id);
			}
		},
		[activeProjects, timer],
	);

	const toggleFocusMode = useCallback(() => {
		// Only open focus mode if timer is running
		setFocusModeOpen((prev) => {
			if (!prev && !timer.isRunning) return false;
			return !prev;
		});
	}, [timer.isRunning]);

	const shortcutActions = useMemo(
		() => ({
			toggleTimer,
			selectProject: selectProjectByIndex,
			openCommandPalette: () => setCommandPaletteOpen(true),
			toggleFocusMode,
		}),
		[toggleTimer, selectProjectByIndex, toggleFocusMode],
	);

	useKeyboardShortcuts(shortcutActions);

	const {
		items: commandItems,
		recencyBoost,
		recordInvocation,
	} = useCommandActions({
		projects: activeProjects.map((p) => ({ id: p.id, name: p.name, color: p.color })),
		isTimerRunning: timer.isRunning,
		onToggleTimer: toggleTimer,
	});

	const timerProps = {
		projects: projectsList,
		isRunning: timer.isRunning,
		selectedProjectId: timer.selectedProjectId,
		elapsedSeconds: timer.elapsedSeconds,
		customStartTime: timer.customStartTime,
		startTimer: timer.startTimer,
		stopTimer: timer.stopTimer,
		selectProject: timer.selectProject,
		setCustomStartTime: timer.setCustomStartTime,
	};

	return (
		<div className="min-h-screen bg-background">
			{/* Desktop sidebar */}
			<Sidebar {...timerProps} />

			{/* Mobile header + drawer */}
			<MobileHeader {...timerProps} />

			{/* Main content area */}
			<main className="lg:ml-64" key={location.pathname}>
				<div style={{ animation: "fadeSlideIn 200ms ease-out both" }}>
					<Outlet />
				</div>
			</main>

			{/* Command palette */}
			<CommandPalette
				open={commandPaletteOpen}
				onClose={() => setCommandPaletteOpen(false)}
				items={commandItems}
				onInvoke={(id) => {
					recordInvocation(id);
					setCommandPaletteOpen(false);
				}}
				recencyBoost={recencyBoost}
			/>

			{/* Focus mode */}
			<FocusMode
				open={focusModeOpen}
				onClose={() => setFocusModeOpen(false)}
				isRunning={timer.isRunning}
				totalSeconds={totalSeconds}
				projectName={selectedProject?.name}
				projectColor={selectedProject?.color}
				onStop={() => {
					timer.stopTimer();
					setFocusModeOpen(false);
				}}
			/>

			{/* Morning briefing */}
			<MorningBriefing
				yesterdayMinutes={(() => {
					const yesterday = new Date();
					yesterday.setDate(yesterday.getDate() - 1);
					yesterday.setHours(0, 0, 0, 0);
					const today = new Date();
					today.setHours(0, 0, 0, 0);
					return (weekSessions ?? [])
						.filter((s) => {
							const d = parseUtcIso(s.startTime);
							return d >= yesterday && d < today;
						})
						.reduce((sum, s) => sum + s.duration, 0);
				})()}
				yesterdaySessionCount={(() => {
					const yesterday = new Date();
					yesterday.setDate(yesterday.getDate() - 1);
					yesterday.setHours(0, 0, 0, 0);
					const today = new Date();
					today.setHours(0, 0, 0, 0);
					return (weekSessions ?? []).filter((s) => {
						const d = parseUtcIso(s.startTime);
						return d >= yesterday && d < today;
					}).length;
				})()}
				todayIntentionCount={(todayIntentions ?? []).length}
				goalWarnings={[]}
			/>

			{/* Weekly review */}
			<WeeklyReviewDialog />

			{/* End-of-day review */}
			<EndOfDayReview
				totalMinutesToday={todayTotalMinutes}
				sessionCount={todaySessionCount}
				topProjectName={topProject}
				existingNote={dailyNote?.note}
				existingMood={dailyNote?.mood ?? undefined}
				onSave={(note, mood) => upsertNote.mutate({ note, mood })}
			/>
		</div>
	);
}
