/**
 * Layout Component
 * Sidebar-based shell with persistent timer for all authenticated pages.
 * Desktop: fixed left sidebar (w-64) + offset main content.
 * Mobile: sticky header with hamburger drawer.
 * Handles favicon indicator, keyboard shortcuts, and command palette.
 */
import { useState, useCallback, useMemo } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { useFavicon, useKeyboardShortcuts } from "@/shared/lib";
import { CommandPalette } from "@/shared/ui";
import { useProjects } from "@/entities/project";
import { useTimer } from "@/features/timer";
import { Sidebar, MobileHeader } from "@/widgets/sidebar";

export function Layout() {
  const { data: projects } = useProjects();
  const timer = useTimer();
  const location = useLocation();
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

  const projectsList = projects || [];
  const activeProjects = projectsList.filter((p) => !p.archived);
  const selectedProject = projectsList.find((p) => p.id === timer.selectedProjectId);

  useFavicon(timer.isRunning, selectedProject?.color);

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
    [activeProjects, timer]
  );

  const shortcutActions = useMemo(
    () => ({
      toggleTimer,
      selectProject: selectProjectByIndex,
      openCommandPalette: () => setCommandPaletteOpen(true),
    }),
    [toggleTimer, selectProjectByIndex]
  );

  useKeyboardShortcuts(shortcutActions);

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
        projects={activeProjects.map((p) => ({ id: p.id, name: p.name, color: p.color }))}
        isTimerRunning={timer.isRunning}
        onToggleTimer={toggleTimer}
      />
    </div>
  );
}
