/**
 * Layout Component
 * Sidebar-based shell with persistent timer for all authenticated pages.
 * Desktop: fixed left sidebar (w-64) + offset main content.
 * Mobile: sticky header with hamburger drawer.
 */
import { Outlet } from "react-router-dom";
import { useProjects } from "@/entities/project";
import { useTimer } from "@/features/timer";
import { Sidebar, MobileHeader } from "@/widgets/sidebar";

export function Layout() {
  const { data: projects } = useProjects();
  const timer = useTimer();

  const projectsList = projects || [];

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
      <main className="lg:ml-64">
        <Outlet />
      </main>
    </div>
  );
}
