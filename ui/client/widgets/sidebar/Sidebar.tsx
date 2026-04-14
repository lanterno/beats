/**
 * Sidebar Component
 * Composite sidebar shell: brand, timer, stats, project navigation.
 * Pinned left on desktop, hidden on mobile (MobileHeader handles mobile).
 */

import { BarChart3, CalendarDays, Download, LogOut, Settings, X } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import type { ProjectWithDuration } from "@/entities/project";
import { clearSessionToken, logout, useAuth } from "@/features/auth";
import { cn, useInstallPrompt, useOnlineStatus } from "@/shared/lib";
import { DeviceStatus } from "./DeviceStatus";
import { SidebarProjectList } from "./SidebarProjectList";
import { SidebarStats } from "./SidebarStats";
import { SidebarTimer, type TimerProps } from "./SidebarTimer";

interface SidebarProps extends TimerProps {
	projects: ProjectWithDuration[];
}

export function Sidebar(props: SidebarProps) {
	const { projects } = props;
	const location = useLocation();
	const navigate = useNavigate();
	const { canShow: canInstall, install, dismiss: dismissInstall } = useInstallPrompt();
	const isOnline = useOnlineStatus();
	const { user } = useAuth();

	const handleLogout = async () => {
		await logout().catch(() => {});
		clearSessionToken();
		navigate("/login");
	};

	return (
		<aside className="hidden lg:flex fixed top-0 left-0 bottom-0 w-64 bg-sidebar border-r border-sidebar-border flex-col z-40">
			{/* Brand + Nav */}
			<div className="px-5 py-4 border-b border-sidebar-border flex items-center justify-between">
				<div className="flex items-center gap-2">
					<Link
						to="/app"
						className="font-heading text-xl font-bold text-sidebar-foreground hover:text-sidebar-primary transition-colors"
					>
						Beats
					</Link>
					{!isOnline && (
						<span
							className="w-2 h-2 rounded-full bg-accent/70 animate-pulse"
							title="Offline — changes will sync when you reconnect"
						/>
					)}
				</div>
				<div className="flex items-center gap-1">
					<Link
						to="/plan"
						className={cn(
							"p-1.5 rounded-md transition-colors",
							location.pathname === "/plan"
								? "bg-sidebar-accent text-sidebar-primary"
								: "text-sidebar-foreground/50 hover:text-sidebar-foreground hover:bg-sidebar-accent/50",
						)}
						title="Weekly Plan"
					>
						<CalendarDays className="w-4 h-4" />
					</Link>
					<Link
						to="/insights"
						className={cn(
							"p-1.5 rounded-md transition-colors",
							location.pathname === "/insights"
								? "bg-sidebar-accent text-sidebar-primary"
								: "text-sidebar-foreground/50 hover:text-sidebar-foreground hover:bg-sidebar-accent/50",
						)}
						title="Insights"
					>
						<BarChart3 className="w-4 h-4" />
					</Link>
					<Link
						to="/settings"
						className={cn(
							"p-1.5 rounded-md transition-colors",
							location.pathname === "/settings"
								? "bg-sidebar-accent text-sidebar-primary"
								: "text-sidebar-foreground/50 hover:text-sidebar-foreground hover:bg-sidebar-accent/50",
						)}
						title="Settings"
					>
						<Settings className="w-4 h-4" />
					</Link>
				</div>
			</div>

			{/* Scrollable content */}
			<div className="flex-1 overflow-y-auto p-4 space-y-5">
				<SidebarTimer {...props} />
				<SidebarStats />
				<SidebarProjectList projects={projects} />
				<DeviceStatus />
			</div>

			{/* Install prompt */}
			{canInstall && (
				<div className="px-4 py-3 border-t border-sidebar-border">
					<div className="flex items-center gap-2">
						<button
							onClick={install}
							className="flex-1 flex items-center gap-2 text-xs text-sidebar-foreground/70 hover:text-sidebar-primary transition-colors"
						>
							<Download className="w-3.5 h-3.5" />
							Install Beats
						</button>
						<button
							onClick={dismissInstall}
							className="p-0.5 text-sidebar-foreground/30 hover:text-sidebar-foreground/60 transition-colors"
						>
							<X className="w-3 h-3" />
						</button>
					</div>
				</div>
			)}

			{/* User + Logout */}
			<div className="px-4 py-3 border-t border-sidebar-border">
				<div className="flex items-center justify-between">
					<span
						className="text-xs text-sidebar-foreground/60 truncate max-w-[160px]"
						title={user?.email}
					>
						{user?.email}
					</span>
					<button
						onClick={handleLogout}
						className="p-1.5 rounded-md text-sidebar-foreground/40 hover:text-sidebar-foreground hover:bg-sidebar-accent/50 transition-colors"
						title="Sign out"
					>
						<LogOut className="w-3.5 h-3.5" />
					</button>
				</div>
			</div>
		</aside>
	);
}
