/**
 * Layout Component
 * Sidebar-based shell with persistent timer for all authenticated pages.
 * Desktop: fixed left sidebar (w-64) + offset main content.
 * Mobile: sticky header with hamburger drawer.
 * Handles favicon indicator, keyboard shortcuts, command palette, and focus mode.
 */
import { useCallback, useMemo, useState } from "react";
import { Outlet, useLocation } from "react-router";
import { useProjects, visibleProjects } from "@/entities/project";
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
import { CommandPalette, FocusMode } from "@/shared/ui";
import { MobileHeader, Sidebar } from "@/widgets/sidebar";

export function Layout() {
	const { data: projects } = useProjects();
	const timer = useTimer();
	const location = useLocation();
	const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
	const [focusModeOpen, setFocusModeOpen] = useState(false);

	// Initialize theme + density from localStorage
	useTheme();

	// Start the offline mutation sync engine exactly once.
	useSyncEngine();

	const projectsList = projects || [];
	const activeProjects = visibleProjects(projectsList);
	const selectedProject = projectsList.find((p) => p.id === timer.selectedProjectId);

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
		</div>
	);
}
