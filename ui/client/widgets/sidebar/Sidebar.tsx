/**
 * Sidebar Component
 * Composite sidebar shell: brand, timer, stats, project navigation.
 * Pinned left on desktop, hidden on mobile (MobileHeader handles mobile).
 */
import { Link, useLocation } from "react-router-dom";
import { BarChart3 } from "lucide-react";
import { cn } from "@/shared/lib";
import type { ProjectWithDuration } from "@/entities/project";
import { SidebarTimer, type TimerProps } from "./SidebarTimer";
import { SidebarStats } from "./SidebarStats";
import { SidebarProjectList } from "./SidebarProjectList";

interface SidebarProps extends TimerProps {
  projects: ProjectWithDuration[];
}

export function Sidebar(props: SidebarProps) {
  const { projects } = props;
  const location = useLocation();

  return (
    <aside className="hidden lg:flex fixed top-0 left-0 bottom-0 w-64 bg-sidebar border-r border-sidebar-border flex-col z-40">
      {/* Brand + Nav */}
      <div className="px-5 py-4 border-b border-sidebar-border flex items-center justify-between">
        <Link
          to="/"
          className="font-heading text-xl font-bold text-sidebar-foreground hover:text-sidebar-primary transition-colors"
        >
          Beats
        </Link>
        <Link
          to="/insights"
          className={cn(
            "p-1.5 rounded-md transition-colors",
            location.pathname === "/insights"
              ? "bg-sidebar-accent text-sidebar-primary"
              : "text-sidebar-foreground/50 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
          )}
          title="Insights"
        >
          <BarChart3 className="w-4 h-4" />
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
