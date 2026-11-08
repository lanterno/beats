/**
 * The control plane's shell: a sidebar over the sky, as the app has it, and
 * one thing the app does not: "Back office" on every page at every width, so
 * an operator is never unsure which surface they are on.
 */

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, NavLink, Route, Routes } from "react-router";
import { Abuse } from "@/pages/Abuse";
import { Account, Accounts } from "@/pages/Accounts";
import { Attention } from "@/pages/Attention";
import { Capacity } from "@/pages/Capacity";
import { Compliance } from "@/pages/Compliance";
import { Organisation, Organisations } from "@/pages/Organisations";
import { get } from "@/shared/api/client";
import type { OperatorMe } from "@/shared/api/schema";
import { APP_NAME } from "@/shared/config/brand";
import { applyHour, type Hour, readHour } from "@/shared/lib/hour";
import {
	BellIcon,
	BrandMark,
	BuildingIcon,
	ClipboardIcon,
	DatabaseIcon,
	MonitorIcon,
	MoonIcon,
	PersonIcon,
	ShieldIcon,
	SunIcon,
} from "@/shared/ui/icons";

const queryClient = new QueryClient({
	defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

const PLACES = [
	{ to: "/", label: "Attention", Icon: BellIcon },
	{ to: "/accounts", label: "Accounts", Icon: PersonIcon },
	{ to: "/organisations", label: "Organisations", Icon: BuildingIcon },
	{ to: "/abuse", label: "Abuse", Icon: ShieldIcon },
	{ to: "/capacity", label: "Capacity", Icon: DatabaseIcon },
	{ to: "/compliance", label: "Compliance", Icon: ClipboardIcon },
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

function Shell() {
	const me = useQuery({ queryKey: ["me"], queryFn: () => get<OperatorMe>("/api/operator/me") });
	return (
		<div className="min-h-screen lg:flex">
			<aside className="sticky top-0 z-10 flex flex-col gap-2.5 bg-panel-solid px-4 pt-3 pb-2 shadow-[var(--shadow-hairline)] lg:h-screen lg:w-[236px] lg:shrink-0 lg:gap-6 lg:bg-sidebar lg:px-3 lg:py-5 lg:shadow-none">
				<div className="flex items-center gap-2.5 lg:px-2">
					<BrandMark className="size-10 shrink-0" />
					<div className="flex items-center gap-2 lg:flex-col lg:items-start lg:gap-1">
						<span className="font-heading text-[17px] leading-none font-extrabold">{APP_NAME}</span>
						<span className="rounded-full bg-ink px-2 py-0.5 text-[12px] leading-tight font-bold text-panel-solid">
							Back office
						</span>
					</div>
				</div>
				<nav className="-mx-4 flex gap-1 overflow-x-auto px-4 lg:mx-0 lg:flex-col lg:overflow-visible lg:px-0">
					{PLACES.map(({ to, label, Icon }) => (
						<NavLink
							key={to}
							to={to}
							end={to === "/"}
							className={({ isActive }) =>
								`flex h-11 shrink-0 items-center gap-2.5 rounded-full px-3.5 text-[14px] lg:h-10 ${isActive ? "bg-wash-strong font-bold" : "hover:bg-wash"}`
							}
						>
							<Icon />
							{label}
						</NavLink>
					))}
				</nav>
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
				<div className="mx-auto max-w-[var(--content-max)]">
					<Routes>
						<Route path="/" element={<Attention />} />
						<Route path="/accounts" element={<Accounts />} />
						<Route path="/accounts/:id" element={<Account />} />
						<Route path="/organisations" element={<Organisations />} />
						<Route path="/organisations/:id" element={<Organisation />} />
						<Route path="/abuse" element={<Abuse />} />
						<Route path="/capacity" element={<Capacity />} />
						<Route path="/compliance" element={<Compliance />} />
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
