/**
 * Sidebar Component
 * Composite sidebar shell: brand, places, timer, search, stats, projects, utilities.
 * Pinned left on desktop, hidden on mobile (MobileHeader handles mobile).
 *
 * The fixed `w-72` slot is the geometry Layout offsets `main` by; inside it
 * the column floats as a rounded panel with a gutter of air, the way the
 * mockup's `.sidebar` sits beside the page — no border, no edge.
 *
 * Nothing in the column scrolls, and the order is how often a thing is
 * reached. The five places people move between all day — Today, Projects,
 * Weekly plan, Insights, Coach — are one row of large icons at the top,
 * named by their tooltip; the timer sits straight under them; and the three
 * utilities — Clients, Organisations, Settings — are a smaller row of their
 * own at the foot, above the line that signs out. The project list is the one
 * part that would grow without bound, so it is capped (`PROJECTS_SHOWN`) with
 * the Projects icon as the way to the rest, and clips rather than scrolls on
 * a short viewport.
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
import { BrandMark, SyncStatus, Tooltip, TooltipContent, TooltipTrigger } from "@/shared/ui";
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

/** How many projects the rail names before the Projects page takes over. */
const PROJECTS_SHOWN = 6;

/** The places, the top row: where people move between all day. */
const NAV = [
	{ to: "/app", title: "Today", Icon: Sun, prefix: false },
	{ to: "/projects", title: "Projects", Icon: Layers, prefix: true },
	{ to: "/plan", title: "Weekly plan", Icon: CalendarDays, prefix: false },
	{ to: "/insights", title: "Insights", Icon: BarChart3, prefix: true },
	{ to: "/coach", title: "Coach", Icon: Sparkles, prefix: false },
] as const;

/** The utilities, the foot row: reached once in a while, not all day. */
const UTILITIES = [
	// Clients only once there is someone or something to bill (`useShowClients`).
	{ to: "/clients", title: "Clients", Icon: Briefcase, prefix: false },
	{ to: "/organisations", title: "Organisations", Icon: Building2, prefix: true },
	{ to: "/settings", title: "Settings", Icon: Settings, prefix: false },
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

	const nav = NAV.filter((item) => item.to !== "/coach" || coachConfigured === true);
	const utilities = UTILITIES.filter((item) => item.to !== "/clients" || showClients);

	/** The attention a utility wears, and what it says to a screen reader. */
	const attentionFor = (to: string): { count?: number; label: string } | null =>
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
		<aside className="hidden lg:flex fixed top-0 left-0 bottom-0 w-72 p-3 z-40">
			<div className="flex-1 min-h-0 flex flex-col rounded-[1.625rem] bg-sidebar shadow-soft">
				{/* Brand */}
				<div className="flex items-center justify-between gap-2 px-5 pt-5 pb-3">
					<Link
						to="/app"
						className="flex items-center gap-2.5 min-w-0 font-heading text-2xl font-extrabold tracking-[-0.01em] leading-none text-sidebar-foreground hover:text-sidebar-primary transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring rounded-full"
					>
						<BrandMark className="w-9 h-9 shrink-0" />
						<span className="truncate">{APP_NAME}</span>
					</Link>
					<SyncStatus />
				</div>

				{/* The places: one row of large icons, named by their tooltip */}
				<nav aria-label="Pages" className="flex items-center justify-between gap-1 px-4 pb-3">
					{nav.map(({ to, title, Icon, prefix }) => {
						const active = isActive(to, prefix);
						return (
							<Tooltip key={to}>
								<TooltipTrigger asChild>
									<Link
										to={to}
										aria-current={active ? "page" : undefined}
										aria-label={title}
										className={cn(
											"grid place-items-center w-11 h-11 rounded-2xl transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
											active
												? "bg-sidebar-accent text-sidebar-primary shadow-[inset_0_-3px_0_hsl(var(--accent))]"
												: "text-sidebar-foreground/70 hover:bg-secondary hover:text-sidebar-foreground",
										)}
									>
										<Icon className="w-5 h-5" />
									</Link>
								</TooltipTrigger>
								<TooltipContent side="bottom">{title}</TooltipContent>
							</Tooltip>
						);
					})}
				</nav>

				{/* The timer, straight under the places */}
				<div className="px-5 pb-3">
					<SidebarTimer {...props} />
				</div>

				{/* Search */}
				{onOpenCommandPalette && (
					<div className="px-5 pb-3">
						<button
							type="button"
							onClick={onOpenCommandPalette}
							className="flex w-full items-center gap-2 rounded-full bg-secondary px-4 py-2.5 text-[13px] text-muted-foreground hover:text-sidebar-foreground transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
						>
							<Search className="w-3.5 h-3.5 shrink-0" />
							<span className="flex-1 text-left">Search &amp; commands</span>
							<kbd className="rounded-md border border-border bg-card px-1.5 font-heading text-[11px] text-muted-foreground">
								⌘K
							</kbd>
						</button>
					</div>
				)}

				{/* Stats */}
				<div className="px-5 pb-3">
					<SidebarStats />
				</div>

				{/*
				  The projects, capped: the one region that would grow without
				  bound, so it takes the slack and clips instead of scrolling.
				*/}
				<div className="flex-1 min-h-0 overflow-hidden px-3">
					<SidebarProjectList projects={projects} limit={PROJECTS_SHOWN} />
				</div>

				{/* Install prompt */}
				{canInstall && (
					<div className="px-5 pt-2">
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

				{/* The foot: the wall clock, the utilities, then the account */}
				<div className="px-5 pt-3 pb-4 mt-2 border-t border-border space-y-2">
					<DeviceStatus />

					{/* The utilities, a line of their own */}
					<nav aria-label="Utilities" className="flex items-center gap-1.5">
						{utilities.map(({ to, title, Icon, prefix }) => {
							const attention = attentionFor(to);
							return (
								<Tooltip key={to}>
									<TooltipTrigger asChild>
										<Link
											to={to}
											aria-current={isActive(to, prefix) ? "page" : undefined}
											aria-label={attention?.label ?? title}
											className={cn(
												"relative grid place-items-center w-9 h-9 rounded-full transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
												isActive(to, prefix)
													? "bg-sidebar-accent text-sidebar-primary"
													: "text-sidebar-foreground/70 hover:bg-secondary hover:text-sidebar-foreground",
											)}
										>
											<Icon className="w-4 h-4" />
											{attention && (
												<span
													aria-hidden="true"
													className={cn(
														"absolute -top-0.5 -right-0.5 rounded-full bg-destructive ring-2 ring-sidebar",
														attention.count
															? "min-w-4 px-1 font-heading text-[10px] font-bold leading-4 text-destructive-foreground"
															: "w-2.5 h-2.5",
													)}
												>
													{attention.count}
												</span>
											)}
										</Link>
									</TooltipTrigger>
									<TooltipContent side="top">{title}</TooltipContent>
								</Tooltip>
							);
						})}
					</nav>

					{/* The account, the last line */}
					<div className="flex items-center justify-between gap-2">
						<span className="text-xs text-muted-foreground truncate min-w-0" title={user?.email}>
							{user?.email}
						</span>
						<Tooltip>
							<TooltipTrigger asChild>
								<button
									type="button"
									onClick={handleLogout}
									aria-label="Sign out"
									className="grid place-items-center w-8 h-8 shrink-0 rounded-full text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-secondary transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
								>
									<LogOut className="w-4 h-4" />
								</button>
							</TooltipTrigger>
							<TooltipContent side="top">Sign out</TooltipContent>
						</Tooltip>
					</div>
				</div>
			</div>
		</aside>
	);
}
