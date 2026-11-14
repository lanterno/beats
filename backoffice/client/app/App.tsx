/**
 * The control plane's shell: a sidebar over the sky, as the app has it, and
 * one thing the app does not: "Back office" on every page at every width, so
 * an operator is never unsure which surface they are on.
 *
 * The sidebar is grouped by the question being asked — what is happening now,
 * who it is happening to, what the platform is doing, what we promised —
 * because the pages are reached by the job in hand and not by collection
 * (roadmaps/backoffice.md, stage 1). A place appears here only once its page
 * is built: a nav entry to a screen that does not exist yet is a promise the
 * API cannot keep.
 */

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, NavLink, Route, Routes } from "react-router";
import { Palette } from "@/app/Palette";
import { Access } from "@/pages/Access";
import { Account } from "@/pages/Account";
import { Accounts } from "@/pages/Accounts";
import { Audit } from "@/pages/Audit";
import { Capacity } from "@/pages/Capacity";
import { Compliance } from "@/pages/Compliance";
import { Jobs } from "@/pages/Jobs";
import { Organisation, Organisations } from "@/pages/Organisations";
import { Queue } from "@/pages/Queue";
import { Review } from "@/pages/Review";
import { RunbookPage, Runbooks } from "@/pages/Runbooks";
import { Today } from "@/pages/Today";
import { Trust } from "@/pages/Trust";
import { get } from "@/shared/api/client";
import type { AttentionCounts, OperatorMe } from "@/shared/api/schema";
import { APP_NAME } from "@/shared/config/brand";
import { applyHour, type Hour, readHour } from "@/shared/lib/hour";
import { deployment } from "@/shared/lib/where";
import {
	BellIcon,
	BrandMark,
	BuildingIcon,
	ClipboardIcon,
	ClockIcon,
	DatabaseIcon,
	LinesIcon,
	LockIcon,
	MonitorIcon,
	MoonIcon,
	PersonIcon,
	ShieldIcon,
	SunIcon,
} from "@/shared/ui/icons";

const queryClient = new QueryClient({
	defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

/** A nav entry's badge, when the landing page's counts carry one for it. */
type Badge = (counts: AttentionCounts) => number;

const GROUPS = [
	{
		label: "Now",
		items: [
			{ to: "/", label: "Today", Icon: SunIcon },
			{
				to: "/queue",
				label: "Work queue",
				Icon: BellIcon,
				badge: ((counts) => Object.values(counts).reduce((sum, n) => sum + n, 0)) satisfies Badge,
			},
		],
	},
	{
		label: "People",
		items: [
			{ to: "/accounts", label: "Accounts", Icon: PersonIcon },
			{ to: "/organisations", label: "Organisations", Icon: BuildingIcon },
			{ to: "/trust", label: "Trust and safety", Icon: ShieldIcon },
		],
	},
	{
		label: "Platform",
		items: [
			{
				to: "/jobs",
				label: "Jobs and windows",
				Icon: ClockIcon,
				// What is unfinished: waiting out a window, or stopped and needing
				// somebody. Done jobs are history and belong on the page, not here.
				badge: ((counts) => counts.jobs_queued + counts.jobs_failed) satisfies Badge,
			},
			{ to: "/capacity", label: "Capacity and cost", Icon: DatabaseIcon },
		],
	},
	{
		label: "Governance",
		items: [
			{ to: "/compliance", label: "Privacy and compliance", Icon: LockIcon },
			{ to: "/audit", label: "Audit log", Icon: LinesIcon },
			{ to: "/runbooks", label: "Runbooks", Icon: ClipboardIcon },
			{ to: "/access", label: "Access and controls", Icon: ShieldIcon },
		],
	},
] as const;

const HOURS = [
	{ id: "afternoon", label: "Afternoon", Icon: SunIcon },
	{ id: "dusk", label: "Dusk", Icon: MoonIcon },
	{ id: "system", label: "Follow the system", Icon: MonitorIcon },
] as const;

function HourPicker() {
	const [hour, setHour] = useState<Hour>(readHour);
	return (
		// biome-ignore lint/a11y/useSemanticElements: a fieldset cannot be a rounded flex track across browsers
		<div
			role="group"
			aria-label="Appearance"
			className="flex self-start rounded-full bg-wash p-0.5"
		>
			{HOURS.map(({ id, label, Icon }) => (
				<button
					key={id}
					type="button"
					title={label}
					aria-label={label}
					aria-pressed={hour === id}
					onClick={() => {
						setHour(id);
						applyHour(id);
					}}
					className={`flex size-10 items-center justify-center rounded-full ${hour === id ? "bg-panel-solid shadow-[var(--shadow-hairline)]" : ""}`}
				>
					<Icon />
				</button>
			))}
		</div>
	);
}

/**
 * Which deployment this is, said on every page. On a surface whose buttons
 * suspend people and queue erasures, "am I on production?" must never be a
 * question answered by reading the URL bar.
 */
function Where() {
	const where = deployment(window.location.hostname);
	return (
		<span
			className={`inline-flex h-8 items-center rounded-full px-3 text-[13px] font-bold whitespace-nowrap ${
				where.live ? "bg-ink text-panel-solid" : "bg-wash-strong text-ink"
			}`}
		>
			{where.label}
		</span>
	);
}

/**
 * Above every page: where you are, and the palette. The mock's incidents
 * chip is not built, and on this surface a control that does nothing is
 * worse than no control at all.
 */
function Topbar() {
	return (
		<div className="mb-6 flex flex-wrap items-center gap-2.5">
			<Where />
			<Palette />
		</div>
	);
}

function Nav() {
	const attention = useQuery({
		queryKey: ["attention"],
		queryFn: () => get<AttentionCounts>("/api/operator/attention"),
	});
	return (
		<nav
			aria-label="Back office"
			className="-mx-4 flex gap-1 overflow-x-auto px-4 lg:mx-0 lg:flex-col lg:gap-3 lg:overflow-visible lg:px-0"
		>
			{GROUPS.map((group) => (
				<div key={group.label} className="flex shrink-0 gap-1 lg:flex-col lg:gap-0.5">
					<p className="hidden px-3.5 pb-1 text-[12px] text-ink-muted lg:block">{group.label}</p>
					{group.items.map((item) => {
						const count = "badge" in item && attention.data ? item.badge(attention.data) : 0;
						return (
							<NavLink
								key={item.to}
								to={item.to}
								end={item.to === "/"}
								className={({ isActive }) =>
									`flex h-11 shrink-0 items-center gap-2.5 rounded-full px-3.5 text-[14px] lg:h-10 ${isActive ? "bg-wash-strong font-bold" : "hover:bg-wash"}`
								}
							>
								<item.Icon />
								{item.label}
								{count > 0 ? (
									<span className="ml-auto pl-2 font-heading text-[13px] font-bold">{count}</span>
								) : null}
							</NavLink>
						);
					})}
				</div>
			))}
		</nav>
	);
}

function Shell() {
	const me = useQuery({ queryKey: ["me"], queryFn: () => get<OperatorMe>("/api/operator/me") });
	return (
		<div className="min-h-screen lg:flex">
			<aside className="sticky top-0 z-10 flex flex-col gap-2.5 bg-panel-solid px-4 pt-3 pb-2 shadow-[var(--shadow-hairline)] lg:h-screen lg:w-[236px] lg:shrink-0 lg:gap-6 lg:overflow-y-auto lg:bg-sidebar lg:px-3 lg:py-5 lg:shadow-none">
				<div className="flex items-center gap-2.5 lg:px-2">
					<BrandMark className="size-10 shrink-0" />
					<div className="flex items-center gap-2 lg:flex-col lg:items-start lg:gap-1">
						<span className="font-heading text-[17px] leading-none font-extrabold">{APP_NAME}</span>
						<span className="rounded-full bg-ink px-2 py-0.5 text-[12px] leading-tight font-bold text-panel-solid">
							Back office
						</span>
					</div>
				</div>
				<Nav />
				<footer className="mt-auto hidden flex-col gap-2.5 lg:flex lg:px-2">
					<HourPicker />
					{me.data ? (
						<p className="text-[13px] leading-snug">
							<span className="block truncate" title={me.data.email}>
								{me.data.email}
							</span>
							<span className="text-ink-muted">{me.data.role}</span>
						</p>
					) : null}
				</footer>
			</aside>
			<main className="min-w-0 flex-1 px-4 py-6 sm:px-8 sm:py-8">
				<div className="mx-auto max-w-[1148px]">
					<Topbar />
					<Routes>
						<Route path="/" element={<Today />} />
						<Route path="/queue" element={<Queue />} />
						<Route path="/accounts" element={<Accounts />} />
						<Route path="/accounts/:id" element={<Account />} />
						<Route path="/review/:command/:subject" element={<Review />} />
						<Route path="/organisations" element={<Organisations />} />
						<Route path="/organisations/:id" element={<Organisation />} />
						<Route path="/trust" element={<Trust />} />
						<Route path="/capacity" element={<Capacity />} />
						<Route path="/jobs" element={<Jobs />} />
						<Route path="/compliance" element={<Compliance />} />
						<Route path="/audit" element={<Audit />} />
						<Route path="/runbooks" element={<Runbooks />} />
						<Route path="/access" element={<Access />} />
						<Route path="/runbooks/:id" element={<RunbookPage />} />
					</Routes>
				</div>
			</main>
		</div>
	);
}

export function App() {
	return (
		<QueryClientProvider client={queryClient}>
			<BrowserRouter>
				<Shell />
			</BrowserRouter>
		</QueryClientProvider>
	);
}
