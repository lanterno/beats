/**
 * Sidebar Component
 * Composite sidebar shell: brand, timer, stats, project navigation.
 * Pinned left on desktop, hidden on mobile (MobileHeader handles mobile).
 */
import { Link } from "react-router-dom";
import type { ProjectWithDuration } from "@/entities/project";
import { SidebarTimer, type TimerProps } from "./SidebarTimer";
import { SidebarStats } from "./SidebarStats";
import { SidebarProjectList } from "./SidebarProjectList";

interface SidebarProps extends TimerProps {
  projects: ProjectWithDuration[];
}

export function Sidebar(props: SidebarProps) {
  const { projects } = props;

  return (
    <aside className="hidden lg:flex fixed top-0 left-0 bottom-0 w-64 bg-sidebar border-r border-sidebar-border flex-col z-40">
      {/* Brand */}
      <div className="px-5 py-4 border-b border-sidebar-border">
        <Link
          to="/"
          className="font-heading text-xl font-bold text-sidebar-foreground hover:text-sidebar-primary transition-colors"
        >
          Beats
        </Link>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        <SidebarTimer {...props} />
        <SidebarStats />
        <SidebarProjectList projects={projects} />
      </div>
    </aside>
  );
}
