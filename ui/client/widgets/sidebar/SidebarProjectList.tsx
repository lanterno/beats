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
import { useNavigate, useParams } from "react-router";
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

const HEADING = "text-muted-foreground text-[9.5px] font-bold uppercase tracking-[0.14em]";

// The mockup's `.plist .p .dot`: a soft ring in the panel's own colour lifts the
// dot off the wash. A literal white turned into pale rims on the dusk panel.
const DOT = "w-[11px] h-[11px] rounded-full shrink-0 shadow-[0_0_0_3px_hsl(var(--card)/.6)]";

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
			<div className="flex items-center justify-between mb-1 px-2.5">
				<p className={HEADING}>Projects</p>
				<button
					type="button"
					onClick={() => setDialogOpen(true)}
					aria-label="New project"
					title="New project"
					className="grid place-items-center w-6 h-6 rounded-full text-sidebar-foreground/60 hover:text-sidebar-primary hover:bg-sidebar-accent transition-colors"
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
						// FF.10: padding moved from the wrapper to the navigate button so
						// clicks on the px-2/py-1.5 region also navigate (the wrapper had
						// dead zones at the edges where neither child handled the click).
						<div
							key={project.id}
							className={cn(
								"group w-full flex items-center rounded-full transition-colors",
								isActive
									? "bg-sidebar-accent text-sidebar-foreground font-bold"
									: "hover:bg-secondary text-muted-foreground hover:text-sidebar-foreground",
							)}
						>
							<button
								type="button"
								onClick={() => navigate(`/project/${project.id}`)}
								className="flex items-center gap-2 flex-1 min-w-0 text-left text-[13px] pl-2.5 pr-1 py-1.5 rounded-full focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
							>
								{/* A quiet project dims its dot, not its row: the name is already the muted ink. */}
								<div
									className={cn(DOT, isInactive && !isActive && "opacity-55")}
									style={{ backgroundColor: project.color }}
								/>
								<span className="truncate flex-1 min-w-0">{project.name}</span>
								<span
									className={cn(
										"text-xs font-mono font-bold shrink-0",
										project.weeklyMinutes === 0
											? "text-muted-foreground/50"
											: // On the heavier wash the muted ink is 3.4:1 at dusk.
												isActive
												? "text-foreground/80"
												: "text-muted-foreground",
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
								// FF.10: focus-visible:opacity-100 + group-focus-within
								// reveal the otherwise invisible button when reached by
								// keyboard — was a silent tab stop pre-FF.10.
								className={cn(
									"p-1 mr-1.5 rounded-full transition-all shrink-0 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
									pinned
										? "text-accent-ink"
										: "text-muted-foreground/50 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100 hover:text-accent-ink",
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
				{/* FF.10: only show the New-project empty-state when there are
				    truly NO projects (active or archived). A user with only
				    archived projects sees the "Archived (N)" rail below and
				    the CTA at the top header (+) — pre-FF.10 the empty-state
				    contradicted itself by claiming "no projects" above an
				    archived rail listing the projects. */}
				{sortedVisible.length === 0 && sortedArchived.length === 0 && (
					<button
						type="button"
						onClick={() => setDialogOpen(true)}
						className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-full text-[13px] text-muted-foreground hover:bg-secondary hover:text-sidebar-foreground transition-colors text-left"
					>
						<Plus className="w-3.5 h-3.5 shrink-0" />
						<span>New project</span>
					</button>
				)}
			</nav>

			{sortedArchived.length > 0 && (
				<div className="mt-3">
					<button
						type="button"
						onClick={() => setShowArchived((v) => !v)}
						aria-expanded={showArchived}
						className={cn(
							HEADING,
							"w-full flex items-center gap-1.5 px-2.5 py-1 hover:text-foreground transition-colors",
						)}
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
										type="button"
										key={project.id}
										onClick={() => navigate(`/project/${project.id}`)}
										className={cn(
											"w-full flex items-center gap-2 pl-2.5 pr-2 py-1.5 rounded-full text-[13px] transition-colors text-left opacity-70",
											isActive
												? "bg-sidebar-accent text-sidebar-foreground font-bold"
												: "hover:bg-secondary text-muted-foreground hover:text-sidebar-foreground",
										)}
									>
										<div className={DOT} style={{ backgroundColor: project.color }} />
										<span className="truncate flex-1 min-w-0">{project.name}</span>
										<span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-px rounded-full bg-secondary text-muted-foreground shrink-0">
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
