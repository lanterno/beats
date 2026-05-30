/**
 * Sidebar Project List Component
 * Compact project navigation with weekly hours for each project.
 *
 * P0.3: archived projects are hidden by default. A "Show archived" toggle
 * brings them back as a dimmed group with an explicit "Archived" chip —
 * the escape hatch a user needs to find an archived project to restore it
 * (the full /projects index is deferred to P3.1).
 */
import { ChevronDown, ChevronRight, Plus, Star } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
	NewProjectDialog,
	type ProjectWithDuration,
	partitionByArchived,
	sortProjectsForList,
	usePinnedProjects,
} from "@/entities/project";
import { cn, formatDuration } from "@/shared/lib";

interface SidebarProjectListProps {
	projects: ProjectWithDuration[];
}

export function SidebarProjectList({ projects }: SidebarProjectListProps) {
	const navigate = useNavigate();
	const { projectId: activeProjectId } = useParams<{ projectId: string }>();
	const [dialogOpen, setDialogOpen] = useState(false);
	const [showArchived, setShowArchived] = useState(false);
	const { pins, toggle: togglePinId, isPinned } = usePinnedProjects();

	const { visible, archived } = partitionByArchived(projects);
	const sortedVisible = sortProjectsForList(visible, { pinnedIds: pins });
	const sortedArchived = sortProjectsForList(archived);

	const isActiveProject = (id: string) => id === activeProjectId;

	return (
		<div>
			<div className="flex items-center justify-between mb-2 px-2">
				<p className="text-muted-foreground text-[10px] uppercase tracking-[0.14em]">Projects</p>
				<button
					type="button"
					onClick={() => setDialogOpen(true)}
					aria-label="New project"
					title="New project"
					className="p-0.5 rounded text-sidebar-foreground/50 hover:text-sidebar-primary hover:bg-sidebar-accent/50 transition-colors"
				>
					<Plus className="w-3.5 h-3.5" />
				</button>
			</div>
			<nav className="space-y-0.5">
				{sortedVisible.map((project) => {
					const isActive = isActiveProject(project.id);
					const isInactive = project.weeklyMinutes === 0;
					const pinned = isPinned(project.id);

					return (
						<div
							key={project.id}
							className={cn(
								"group w-full flex items-center gap-2 px-2 py-1.5 rounded-md transition-colors",
								isActive
									? "bg-sidebar-accent text-sidebar-foreground"
									: "hover:bg-sidebar-accent/50 text-sidebar-foreground",
								isInactive && !isActive && "opacity-45",
							)}
						>
							<button
								type="button"
								onClick={() => navigate(`/project/${project.id}`)}
								className="flex items-center gap-2 flex-1 min-w-0 text-left text-sm"
							>
								<div
									className="w-2 h-2 rounded-full shrink-0"
									style={{ backgroundColor: project.color }}
								/>
								<span className="truncate flex-1 min-w-0">{project.name}</span>
								<span
									className={cn(
										"text-xs tabular-nums shrink-0",
										project.weeklyMinutes > 0
											? "text-muted-foreground"
											: "text-muted-foreground/40",
									)}
								>
									{project.weeklyMinutes > 0 ? formatDuration(project.weeklyMinutes) : "—"}
								</span>
							</button>
							<button
								type="button"
								onClick={() => togglePinId(project.id)}
								aria-label={pinned ? `Unpin ${project.name}` : `Pin ${project.name}`}
								aria-pressed={pinned}
								title={pinned ? "Unpin from top" : "Pin to top"}
								className={cn(
									"p-1 rounded transition-all shrink-0 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40",
									pinned
										? "text-accent"
										: "text-muted-foreground/40 opacity-0 group-hover:opacity-100 hover:text-accent",
								)}
							>
								<Star
									className="w-3 h-3"
									fill={pinned ? "currentColor" : "none"}
									aria-hidden="true"
								/>
							</button>
						</div>
					);
				})}
				{sortedVisible.length === 0 && (
					<button
						type="button"
						onClick={() => setDialogOpen(true)}
						className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-sm text-sidebar-foreground/60 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground transition-colors text-left"
					>
						<Plus className="w-3.5 h-3.5 shrink-0" />
						<span>New project</span>
					</button>
				)}
			</nav>

			{sortedArchived.length > 0 && (
				<div className="mt-3 pt-2 border-t border-sidebar-border/60">
					<button
						type="button"
						onClick={() => setShowArchived((v) => !v)}
						aria-expanded={showArchived}
						className="w-full flex items-center gap-1.5 px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-muted-foreground/70 hover:text-muted-foreground transition-colors"
					>
						{showArchived ? (
							<ChevronDown className="w-3 h-3" />
						) : (
							<ChevronRight className="w-3 h-3" />
						)}
						Archived ({sortedArchived.length})
					</button>
					{showArchived && (
						<nav className="mt-1 space-y-0.5">
							{sortedArchived.map((project) => {
								const isActive = isActiveProject(project.id);
								return (
									<button
										key={project.id}
										onClick={() => navigate(`/project/${project.id}`)}
										className={cn(
											"w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors text-left opacity-70",
											isActive
												? "bg-sidebar-accent text-sidebar-foreground"
												: "hover:bg-sidebar-accent/50 text-sidebar-foreground",
										)}
									>
										<div
											className="w-2 h-2 rounded-full shrink-0"
											style={{ backgroundColor: project.color }}
										/>
										<span className="truncate flex-1 min-w-0">{project.name}</span>
										<span className="text-[9px] uppercase tracking-wider px-1 py-0.5 rounded border border-muted-foreground/30 text-muted-foreground shrink-0">
											Arch
										</span>
									</button>
								);
							})}
						</nav>
					)}
				</div>
			)}

			<NewProjectDialog
				open={dialogOpen}
				onClose={() => setDialogOpen(false)}
				onCreated={(project) => navigate(`/project/${project.id}`)}
			/>
		</div>
	);
}
