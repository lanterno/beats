/**
 * Mobile Header Component
 * Sticky top bar for mobile with hamburger menu and mini timer indicator.
 * The bar is a pill floating on the sky; the drawer is the sidebar panel.
 */

import {
	BarChart3,
	CalendarDays,
	Download,
	Layers,
	LogOut,
	Menu,
	Settings,
	Sparkles,
	X,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import type { ProjectWithDuration } from "@/entities/project";
import { useAuth } from "@/features/auth";
import { cn, formatSecondsToTime, parseUtcIso, useInstallPrompt } from "@/shared/lib";
import { signOut } from "@/shared/session";
import { AnimatedDigits, SyncStatus } from "@/shared/ui";
import { DeviceStatus } from "./DeviceStatus";
import { SidebarProjectList } from "./SidebarProjectList";
import { SidebarStats } from "./SidebarStats";
import { SidebarTimer, type TimerProps } from "./SidebarTimer";

interface MobileHeaderProps extends TimerProps {
	projects: ProjectWithDuration[];
}

const NAV = [
	{ to: "/projects", title: "Projects", Icon: Layers },
	{ to: "/plan", title: "Weekly Plan", Icon: CalendarDays },
	{ to: "/coach", title: "Coach", Icon: Sparkles },
	{ to: "/insights", title: "Insights", Icon: BarChart3 },
	{ to: "/settings", title: "Settings", Icon: Settings },
] as const;

export function MobileHeader(props: MobileHeaderProps) {
	const [drawerOpen, setDrawerOpen] = useState(false);
	const navigate = useNavigate();
	const { user } = useAuth();
	const { canShow: canInstall, install, dismiss: dismissInstall } = useInstallPrompt();

	const { isRunning, elapsedSeconds, customStartTime, selectedProjectId, projects } = props;
	const selectedProject = projects.find((p) => p.id === selectedProjectId);

	let totalSeconds = elapsedSeconds;
	if (customStartTime && isRunning) {
		const startDate = parseUtcIso(customStartTime);
		const now = new Date();
		totalSeconds = Math.floor((now.getTime() - startDate.getTime()) / 1000);
	}

	const closeDrawer = () => setDrawerOpen(false);

	const handleLogout = async () => {
		closeDrawer();
		await signOut();
		navigate("/");
	};

	return (
		<>
			<header className="lg:hidden sticky top-3 z-50 mx-3 h-11 rounded-full bg-sidebar shadow-soft backdrop-blur-sm flex items-center justify-between pl-3 pr-4">
				<div className="flex items-center gap-2.5">
					<button
						type="button"
						onClick={() => setDrawerOpen(true)}
						aria-label="Open menu"
						aria-expanded={drawerOpen}
						className="grid place-items-center w-8 h-8 rounded-full text-sidebar-foreground hover:bg-secondary transition-colors"
					>
						<Menu className="w-5 h-5" />
					</button>
					<Link
						to="/app"
						className="font-heading text-base font-extrabold tracking-[-0.01em] text-sidebar-foreground"
					>
						Beats
					</Link>
					<SyncStatus />
				</div>

				{isRunning && selectedProject && (
					<div className="flex items-center gap-2 rounded-full bg-secondary pl-2.5 pr-3 py-1">
						<span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
						<div
							className="w-2 h-2 rounded-full shrink-0"
							style={{ backgroundColor: selectedProject.color }}
						/>
						<AnimatedDigits
							value={formatSecondsToTime(totalSeconds)}
							className="font-mono font-bold text-foreground text-xs"
						/>
					</div>
				)}
			</header>

			{/* Drawer overlay */}
			{drawerOpen && (
				<div className="lg:hidden fixed inset-0 z-[60]">
					<button
						type="button"
						aria-label="Close menu"
						className="absolute inset-0 w-full bg-veil backdrop-blur-xs"
						onClick={closeDrawer}
					/>
					<aside
						className={cn(
							"absolute top-3 left-3 bottom-3 w-72 max-w-[calc(100vw-1.5rem)] rounded-[1.625rem] bg-sidebar shadow-soft",
							"flex flex-col overflow-y-auto",
							"animate-in slide-in-from-left duration-200",
						)}
					>
						<div className="px-4 pt-5 pb-3 space-y-3">
							<div className="flex items-center justify-between px-1">
								<Link
									to="/app"
									onClick={closeDrawer}
									className="font-heading text-[22px] font-extrabold tracking-[-0.01em] leading-none text-sidebar-foreground"
								>
									Beats
								</Link>
								<button
									type="button"
									onClick={closeDrawer}
									className="grid place-items-center w-8 h-8 rounded-full text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
								>
									<X className="w-5 h-5" />
								</button>
							</div>
							<nav aria-label="Pages" className="flex items-center justify-between">
								{NAV.map(({ to, title, Icon }) => (
									<Link
										key={to}
										to={to}
										onClick={closeDrawer}
										className="grid place-items-center w-8 h-8 rounded-full bg-secondary text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
										title={title}
									>
										<Icon className="w-4 h-4" />
									</Link>
								))}
							</nav>
						</div>

						<div className="flex-1 px-4 pb-4 space-y-4">
							<SidebarTimer {...props} />
							<SidebarStats />
							<SidebarProjectList projects={projects} />
							<DeviceStatus />
						</div>

						{/* Install prompt */}
						{canInstall && (
							<div className="px-4 pb-2">
								<div className="flex items-center gap-2 rounded-full bg-secondary px-3 py-1.5">
									<button
										type="button"
										onClick={install}
										className="flex-1 flex items-center gap-2 text-xs font-bold text-sidebar-foreground hover:text-sidebar-primary transition-colors"
									>
										<Download className="w-3.5 h-3.5" />
										Install Beats
									</button>
									<button
										type="button"
										onClick={dismissInstall}
										className="p-0.5 rounded-full text-sidebar-foreground/40 hover:text-sidebar-foreground transition-colors"
									>
										<X className="w-3 h-3" />
									</button>
								</div>
							</div>
						)}

						{/* User + Logout */}
						<div className="px-4 pt-1 pb-4">
							<div className="flex items-center justify-between gap-2">
								<span
									className="text-xs text-muted-foreground truncate min-w-0 pl-1"
									title={user?.email}
								>
									{user?.email}
								</span>
								<button
									type="button"
									onClick={handleLogout}
									className="grid place-items-center w-7 h-7 shrink-0 rounded-full text-sidebar-foreground/50 hover:text-sidebar-foreground hover:bg-secondary transition-colors"
									title="Sign out"
									aria-label="Sign out"
								>
									<LogOut className="w-3.5 h-3.5" />
								</button>
							</div>
						</div>
					</aside>
				</div>
			)}
		</>
	);
}
