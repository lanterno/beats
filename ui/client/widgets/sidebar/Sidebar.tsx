/**
 * Sidebar Component
 * Composite sidebar shell: brand, search, labelled nav, stats, projects, timer.
 * Pinned left on desktop, hidden on mobile (MobileHeader handles mobile).
 *
 * The fixed `w-64` slot is the geometry Layout offsets `main` by; inside it
 * the column floats as a rounded panel with a gutter of air, the way the
 * mockup's `.sidebar` sits beside the page — no border, no edge.
 *
 * The column has three zones (docs/mockups/ux-refresh.html): brand and the
 * search pill fixed at the top, the nav / stats / project list scrolling in
 * the middle, and the timer pinned at the bottom — however long the project
 * list grows, the timer never leaves the screen. Nav rows carry their names:
 * seven identical round icons told apart by tooltips were the old design's
 * biggest usability tax.
 */

import {
	BarChart3,
	Briefcase,
	Building2,
	CalendarDays,
	Download,
	Layers,
	LogOut,
	Search,
	Settings,
	Sparkles,
	Sun,
	X,
} from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router";
import { useCoachStatus } from "@/entities/coach";
import type { ProjectWithDuration } from "@/entities/project";
import { useAuth } from "@/features/auth";
import { APP_NAME } from "@/shared/config";
import { cn, useInstallPrompt } from "@/shared/lib";
import { signOut } from "@/shared/session";
import { BrandMark, SyncStatus } from "@/shared/ui";
import { DeviceStatus } from "./DeviceStatus";
import { SidebarProjectList } from "./SidebarProjectList";
import { SidebarStats } from "./SidebarStats";
import { SidebarTimer, type TimerProps } from "./SidebarTimer";
import { useBillingBudgetAttention } from "./useBillingBudgetAttention";
import { useInvitationAttention } from "./useInvitationAttention";
import { useShowClients } from "./useShowClients";

interface SidebarProps extends TimerProps {
	projects: ProjectWithDuration[];
	onOpenCommandPalette?: () => void;
}

const NAV = [
	{
		group: "Work",
		items: [
			{ to: "/app", title: "Today", Icon: Sun, prefix: false },
			{ to: "/projects", title: "Projects", Icon: Layers, prefix: true },
			{ to: "/plan", title: "Weekly plan", Icon: CalendarDays, prefix: false },
		],
	},
	{
		group: "Understand",
		items: [
			{ to: "/insights", title: "Insights", Icon: BarChart3, prefix: true },
			{ to: "/coach", title: "Coach", Icon: Sparkles, prefix: false },
		],
	},
	{
		group: "Money & people",
		items: [
			// Only once there is someone or something to bill (`useShowClients`); with
			// a dot while a billing budget is used up (`useBillingBudgetAttention`).
			{ to: "/clients", title: "Clients", Icon: Briefcase, prefix: false },
			{ to: "/organisations", title: "Organisations", Icon: Building2, prefix: true },
		],
	},
	{
		group: null,
		items: [{ to: "/settings", title: "Settings", Icon: Settings, prefix: false }],
	},
] as const;

export function Sidebar(props: SidebarProps) {
	const { projects, onOpenCommandPalette } = props;
	const location = useLocation();
	const navigate = useNavigate();
	const { canShow: canInstall, install, dismiss: dismissInstall } = useInstallPrompt();
	const { user } = useAuth();
	const showClients = useShowClients(projects);
	// Coach only on a server that can run it (`useCoachStatus`); until it has
	// answered, no Coach rather than one that comes and goes.
	const { configured: coachConfigured } = useCoachStatus();
	const budgetUsedUp = useBillingBudgetAttention(showClients);
	// With a count while invitations to this account wait (`useInvitationAttention`).
	const invitations = useInvitationAttention();

	const groups = NAV.map(({ group, items }) => ({
		group,
		items: items.filter(
			(item) =>
				(item.to !== "/clients" || showClients) &&
				(item.to !== "/coach" || coachConfigured === true),
		),
	})).filter(({ items }) => items.length > 0);

	const badge = (to: string): { count?: number; label: string } | null =>
		to === "/clients" && budgetUsedUp
			? { label: "Clients, a billing budget is used up" }
			: to === "/organisations" && invitations > 0
				? {
						count: invitations,
						label: `Organisations, ${
							invitations === 1 ? "an invitation is" : `${invitations} invitations are`
						} waiting`,
					}
				: null;

	const handleLogout = async () => {
		await signOut();
		navigate("/");
	};

	const isActive = (to: string, prefix: boolean) =>
		prefix ? location.pathname.startsWith(to) : location.pathname === to;

	return (
		<aside className="hidden lg:flex fixed top-0 left-0 bottom-0 w-64 p-3 z-40">
			<div className="flex-1 min-h-0 flex flex-col rounded-[1.625rem] bg-sidebar shadow-soft">
				{/* Brand + search — fixed at the top */}
				<div className="px-4 pt-5 pb-2 space-y-3">
					<div className="flex items-center justify-between px-1">
						<Link
							to="/app"
							className="flex items-center gap-2.5 font-heading text-[22px] font-extrabold tracking-[-0.01em] leading-none text-sidebar-foreground hover:text-sidebar-primary transition-colors"
						>
							<BrandMark className="w-7 h-7 shrink-0" />
							{APP_NAME}
						</Link>
						<SyncStatus />
					</div>
					{onOpenCommandPalette && (
						<button
							type="button"
							onClick={onOpenCommandPalette}
							className="flex w-full items-center gap-2 rounded-full bg-secondary px-3.5 py-2 text-[13px] text-muted-foreground hover:text-sidebar-foreground transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
						>
							<Search className="w-3.5 h-3.5 shrink-0" />
							<span className="flex-1 text-left">Search &amp; commands</span>
							<kbd className="rounded-md border border-border bg-card px-1.5 font-heading text-[11px] text-muted-foreground">
								⌘K
							</kbd>
						</button>
					)}
				</div>

				{/* Scrollable middle: nav, stats, projects, device */}
				<div className="flex-1 min-h-0 overflow-y-auto px-4 pb-2 space-y-4">
					<nav aria-label="Pages">
						{groups.map(({ group, items }) => (
							<div key={group ?? "footer"}>
								{group && (
									<div className="px-3 pt-3 pb-1 text-[10.5px] font-heading font-bold uppercase tracking-[0.12em] text-muted-foreground">
										{group}
									</div>
								)}
								{items.map(({ to, title, Icon, prefix }) => {
									const attention = badge(to);
									return (
										<Link
											key={to}
											to={to}
											aria-current={isActive(to, prefix) ? "page" : undefined}
											aria-label={attention?.label}
											className={cn(
												"flex items-center gap-2.5 rounded-full px-3 py-2 text-sm transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
												isActive(to, prefix)
													? "bg-sidebar-accent font-bold text-sidebar-foreground shadow-[inset_3px_0_0_hsl(var(--accent))]"
													: "font-medium text-sidebar-foreground/80 hover:bg-secondary hover:text-sidebar-foreground",
											)}
										>
											<Icon className="w-4 h-4 shrink-0" />
											<span className="flex-1 truncate">{title}</span>
											{attention && (
												<span
													aria-hidden="true"
													className={cn(
														"shrink-0 rounded-full bg-destructive",
														attention.count
															? "px-1.5 text-[11px] font-heading font-bold leading-4 text-destructive-foreground"
															: "w-2.5 h-2.5",
													)}
												>
													{attention.count}
												</span>
											)}
										</Link>
									);
								})}
							</div>
						))}
					</nav>
					<SidebarStats />
					<SidebarProjectList projects={projects} />
					<DeviceStatus />
				</div>

				{/* Pinned bottom: the timer never scrolls away */}
				<div className="px-4 pt-3 pb-2 border-t border-border">
					<SidebarTimer {...props} />
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
								Install {APP_NAME}
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
