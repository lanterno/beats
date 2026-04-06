/**
 * Sidebar Project List Component
 * Compact project navigation with weekly hours for each project.
 */
import { useNavigate, useParams } from "react-router-dom";
import { formatDuration } from "@/shared/lib";
import type { ProjectWithDuration } from "@/entities/project";

interface SidebarProjectListProps {
  projects: ProjectWithDuration[];
}

export function SidebarProjectList({ projects }: SidebarProjectListProps) {
  const navigate = useNavigate();
  const { projectId: activeProjectId } = useParams<{ projectId: string }>();

  // Active projects first (by weekly hours desc), then inactive alphabetically
  const active = projects
    .filter((p) => p.weeklyMinutes > 0)
    .sort((a, b) => b.weeklyMinutes - a.weeklyMinutes);
  const inactive = projects
    .filter((p) => p.weeklyMinutes === 0)
    .sort((a, b) => a.name.localeCompare(b.name));
  const sorted = [...active, ...inactive];

  return (
    <div>
      <p className="text-muted-foreground text-[10px] uppercase tracking-[0.14em] mb-2 px-2">
        Projects
      </p>
      <nav className="space-y-0.5">
        {sorted.map((project) => {
          const isActive = project.id === activeProjectId;
          const isInactive = project.weeklyMinutes === 0;

          return (
            <button
              key={project.id}
              onClick={() => navigate(`/project/${project.id}`)}
              className={`
                w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors text-left
                ${isActive ? "bg-sidebar-accent text-sidebar-foreground" : "hover:bg-sidebar-accent/50 text-sidebar-foreground"}
                ${isInactive && !isActive ? "opacity-45" : ""}
              `}
            >
              <div
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: project.color }}
              />
              <span className="truncate flex-1 min-w-0">{project.name}</span>
              <span
                className={`text-xs tabular-nums shrink-0 ${
                  project.weeklyMinutes > 0 ? "text-muted-foreground" : "text-muted-foreground/40"
                }`}
              >
                {project.weeklyMinutes > 0 ? formatDuration(project.weeklyMinutes) : "—"}
              </span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
