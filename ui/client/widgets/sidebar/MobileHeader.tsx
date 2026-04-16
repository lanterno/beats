/**
 * Mobile Header Component
 * Sticky top bar for mobile with hamburger menu and mini timer indicator.
 */

import { BarChart3, Menu, Settings, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { ProjectWithDuration } from "@/entities/project";
import { cn, formatSecondsToTime, parseUtcIso } from "@/shared/lib";
import { AnimatedDigits, SyncStatus } from "@/shared/ui";
import { SidebarProjectList } from "./SidebarProjectList";
import { SidebarStats } from "./SidebarStats";
import { SidebarTimer, type TimerProps } from "./SidebarTimer";

interface MobileHeaderProps extends TimerProps {
	projects: ProjectWithDuration[];
}

export function MobileHeader(props: MobileHeaderProps) {
	const [drawerOpen, setDrawerOpen] = useState(false);

	const { isRunning, elapsedSeconds, customStartTime, selectedProjectId, projects } = props;
	const selectedProject = projects.find((p) => p.id === selectedProjectId);

	let totalSeconds = elapsedSeconds;
	if (customStartTime && isRunning) {
		const startDate = parseUtcIso(customStartTime);
		const now = new Date();
		totalSeconds = Math.floor((now.getTime() - startDate.getTime()) / 1000);
	}

	return (
		<>
			<header className="lg:hidden sticky top-0 z-50 h-12 border-b border-border bg-sidebar/95 backdrop-blur-sm flex items-center justify-between px-4">
				<div className="flex items-center gap-3">
					<button
						onClick={() => setDrawerOpen(true)}
						className="p-1 text-sidebar-foreground hover:text-accent transition-colors"
					>
						<Menu className="w-5 h-5" />
					</button>
					<Link to="/app" className="font-heading text-base font-bold text-sidebar-foreground">
						Beats
					</Link>
					<SyncStatus />
				</div>

				{isRunning && selectedProject && (
					<div className="flex items-center gap-2">
						<span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
						<div
							className="w-2 h-2 rounded-full shrink-0"
							style={{ backgroundColor: selectedProject.color }}
						/>
						<AnimatedDigits
							value={formatSecondsToTime(totalSeconds)}
							className="font-mono text-accent text-xs tabular-nums"
						/>
					</div>
				)}
			</header>

			{/* Drawer overlay */}
			{drawerOpen && (
				<div className="lg:hidden fixed inset-0 z-[60]">
					<div
						className="absolute inset-0 bg-black/50 backdrop-blur-xs"
						onClick={() => setDrawerOpen(false)}
					/>
					<aside
						className={cn(
							"absolute top-0 left-0 bottom-0 w-72 bg-sidebar border-r border-sidebar-border",
							"flex flex-col overflow-y-auto",
							"animate-in slide-in-from-left duration-200",
						)}
					>
						<div className="flex items-center justify-between p-4 border-b border-sidebar-border">
							<Link
								to="/app"
								onClick={() => setDrawerOpen(false)}
								className="font-heading text-lg font-bold text-sidebar-foreground"
							>
								Beats
							</Link>
							<div className="flex items-center gap-1">
								<Link
									to="/insights"
									onClick={() => setDrawerOpen(false)}
									className="p-1.5 rounded-md text-sidebar-foreground/50 hover:text-sidebar-foreground hover:bg-sidebar-accent/50 transition-colors"
									title="Insights"
								>
									<BarChart3 className="w-4 h-4" />
								</Link>
								<Link
									to="/settings"
									onClick={() => setDrawerOpen(false)}
									className="p-1.5 rounded-md text-sidebar-foreground/50 hover:text-sidebar-foreground hover:bg-sidebar-accent/50 transition-colors"
									title="Settings"
								>
									<Settings className="w-4 h-4" />
								</Link>
								<button
									onClick={() => setDrawerOpen(false)}
									className="p-1 text-muted-foreground hover:text-foreground transition-colors"
								>
									<X className="w-5 h-5" />
								</button>
							</div>
						</div>

						<div className="flex-1 p-4 space-y-5">
							<SidebarTimer {...props} />
							<SidebarStats />
							<SidebarProjectList projects={projects} />
						</div>
					</aside>
				</div>
			)}
		</>
	);
}
