/**
 * Project Selector Component
 * Searchable dropdown for selecting a project.
 */
import { useState } from "react";
import { Search, X } from "lucide-react";
import { cn } from "@/shared/lib";
import type { ProjectWithDuration } from "@/entities/project";

interface ProjectSelectorProps {
  projects: ProjectWithDuration[];
  selectedProjectId: string | null;
  onSelect: (projectId: string | null) => void;
  disabled?: boolean;
}

export function ProjectSelector({
  projects,
  selectedProjectId,
  onSelect,
  disabled = false,
}: ProjectSelectorProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  const selectedProject = projects.find((p) => p.id === selectedProjectId);

  const filteredProjects = projects.filter(
    (project) =>
      project.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      project.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="relative">
      <p className="text-muted-foreground text-xs uppercase tracking-[0.12em] mb-2">Project</p>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
        <input
          type="text"
          placeholder={selectedProject ? selectedProject.name : "Search projects..."}
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value);
            setIsDropdownOpen(true);
          }}
          onFocus={() => setIsDropdownOpen(true)}
          disabled={disabled}
          className={cn(
            "w-full rounded-md border border-input bg-background py-2 pl-9 pr-9 text-base text-foreground placeholder:text-muted-foreground",
            "focus:outline-hidden focus:ring-2 focus:ring-accent/20 focus:border-accent/40",
            "disabled:opacity-60 disabled:cursor-not-allowed"
          )}
        />
        {(searchQuery || selectedProjectId) && (
          <button
            onClick={() => {
              setSearchQuery("");
              onSelect(null);
              setIsDropdownOpen(false);
            }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {isDropdownOpen && !disabled && (
        <div className="absolute z-50 left-0 right-0 top-full mt-1 rounded-md border border-border bg-card shadow-lg max-h-44 overflow-y-auto">
          {filteredProjects.length > 0 ? (
            filteredProjects.map((project) => (
              <button
                key={project.id}
                onClick={() => {
                  onSelect(project.id);
                  setSearchQuery("");
                  setIsDropdownOpen(false);
                }}
                disabled={disabled}
                className={cn(
                  "w-full text-left px-3 py-2.5 text-base transition-colors border-b border-border last:border-b-0",
                  selectedProjectId === project.id
                    ? "bg-accent/10 text-foreground font-medium"
                    : "text-foreground hover:bg-secondary/50"
                )}
              >
                {project.name}
              </button>
            ))
          ) : (
            <div className="px-3 py-2.5 text-base text-muted-foreground">No projects found</div>
          )}
        </div>
      )}
    </div>
  );
}
