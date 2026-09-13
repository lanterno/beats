/**
 * Sidebar Component
 * Composite sidebar shell: brand, nav, timer, stats, project navigation.
 * Pinned left on desktop, hidden on mobile (MobileHeader handles mobile).
 *
 * The fixed `w-64` slot is the geometry Layout offsets `main` by; inside it
 * the column floats as a rounded panel with a gutter of air, the way the
 * mockup's `.sidebar` sits beside the page — no border, no edge.
 */

import {
	BarChart3,
	CalendarDays,
	Download,
	Layers,
	LogOut,
	Settings,
	Sparkles,
	X,
} from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router";
import type { ProjectWithDuration } from "@/entities/project";
import { useAuth } from "@/features/auth";
import { cn, useInstallPrompt } from "@/shared/lib";
import { signOut } from "@/shared/session";
import { SyncStatus } from "@/shared/ui";
import { DeviceStatus } from "./DeviceStatus";
import { SidebarProjectList } from "./SidebarProjectList";
import { SidebarStats } from "./SidebarStats";
import { SidebarTimer, type TimerProps } from "./SidebarTimer";

interface SidebarProps extends TimerProps {
	projects: ProjectWithDuration[];
}

const NAV = [
	{ to: "/projects", title: "Projects", Icon: Layers, prefix: true },
	{ to: "/plan", title: "Weekly Plan", Icon: CalendarDays, prefix: false },
	{ to: "/coach", title: "Coach", Icon: Sparkles, prefix: false },
	{ to: "/insights", title: "Insights", Icon: BarChart3, prefix: false },
	{ to: "/settings", title: "Settings", Icon: Settings, prefix: false },
] as const;

export function Sidebar(props: SidebarProps) {
	const { projects } = props;
	const location = useLocation();
	const navigate = useNavigate();
	const { canShow: canInstall, install, dismiss: dismissInstall } = useInstallPrompt();
	const { user } = useAuth();

	const handleLogout = async () => {
		await signOut();
		navigate("/");
	};

	const isActive = (to: string, prefix: boolean) =>
		prefix ? location.pathname.startsWith(to) : location.pathname === to;

	return (
		<aside className="hidden lg:flex fixed top-0 left-0 bottom-0 w-64 p-3 z-40">
			<div className="flex-1 min-h-0 flex flex-col rounded-[1.625rem] bg-sidebar shadow-soft">
				{/* Brand + Nav */}
				<div className="px-4 pt-5 pb-3 space-y-3">
					<div className="flex items-baseline justify-between px-1">
						<Link
							to="/app"
							className="font-heading text-[22px] font-extrabold tracking-[-0.01em] leading-none text-sidebar-foreground hover:text-sidebar-primary transition-colors"
						>
							Beats
						</Link>
						<SyncStatus />
					</div>
					<nav aria-label="Pages" className="flex items-center justify-between">
						{NAV.map(({ to, title, Icon, prefix }) => (
							<Link
								key={to}
								to={to}
								className={cn(
									"grid place-items-center w-8 h-8 rounded-full transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
									isActive(to, prefix)
										? "bg-sidebar-accent text-sidebar-primary"
										: "bg-secondary text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground",
								)}
								title={title}
							>
								<Icon className="w-4 h-4" />
							</Link>
						))}
					</nav>
				</div>

				{/* Scrollable content */}
				<div className="flex-1 overflow-y-auto px-4 pb-4 space-y-4">
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
						>
							<LogOut className="w-3.5 h-3.5" />
						</button>
					</div>
				</div>
			</div>
		</aside>
	);
}
