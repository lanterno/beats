/**
 * The row over every page: the "Back office" mark at every width, who is
 * signed in and what their role lets them do, and the hour. On a narrow
 * window it also carries the mark beside the app's name and a strip of the
 * places, since the sidebar is not drawn there.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink } from "react-router";
import { get } from "@/shared/api/client";
import type { OperatorMe } from "@/shared/api/schema";
import { APP_NAME } from "@/shared/config/brand";
import { applyHour, type Hour, readHour } from "@/shared/lib/hour";
import { Chip } from "@/shared/ui";
import { BrandMark, MonitorIcon, MoonIcon, SunIcon } from "@/shared/ui/icons";
import { PLACES } from "./places";
import { BackOfficeMark } from "./Sidebar";

const HOURS = [
	{ id: "afternoon", label: "Afternoon", Icon: SunIcon },
	{ id: "dusk", label: "Dusk", Icon: MoonIcon },
	{ id: "system", label: "Follow the system", Icon: MonitorIcon },
] as const;

function HourPicker() {
	const [hour, setHour] = useState<Hour>(readHour);
	return (
		// biome-ignore lint/a11y/useSemanticElements: a fieldset cannot be a rounded flex track across browsers
		<div role="group" aria-label="Appearance" className="flex rounded-full bg-wash p-0.5">
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
					className={`flex size-9 items-center justify-center rounded-full ${hour === id ? "bg-panel-solid shadow-[var(--shadow-hairline)]" : ""}`}
				>
					<Icon className="size-4" />
				</button>
			))}
		</div>
	);
}

/** Who is signed in, and whether they can act: a viewer reads every page
 * and runs no command, and should know that before a button refuses them. */
function Operator() {
	const me = useQuery({ queryKey: ["me"], queryFn: () => get<OperatorMe>("/api/operator/me") });
	if (!me.data) return null;
	const viewer = me.data.role === "viewer";
	return (
		<div className="flex min-w-0 items-center gap-2 text-[13px]">
			<span className="hidden truncate md:block" title={me.data.email}>
				{me.data.email}
			</span>
			<Chip tone={viewer ? "quiet" : "good"}>
				{viewer ? "Viewer: reads, never acts" : "Operator"}
			</Chip>
		</div>
	);
}

export function Topbar() {
	return (
		<header className="sticky top-0 z-10 flex flex-col gap-2.5 bg-panel px-4 pt-3 pb-2 shadow-[var(--shadow-hairline)] sm:px-8 lg:bg-transparent lg:pt-5 lg:pb-0 lg:shadow-none">
			<div className="flex items-center justify-between gap-4">
				<div className="flex min-w-0 items-center gap-2.5">
					<BrandMark className="size-9 shrink-0 lg:hidden" />
					<span className="hidden font-heading text-[17px] leading-none font-extrabold sm:block lg:hidden">
						{APP_NAME}
					</span>
					<BackOfficeMark className="lg:hidden" />
					<p className="hidden text-[14px] text-ink-muted lg:block">
						Operational metadata, never what anyone tracked.
					</p>
				</div>
				<div className="flex shrink-0 items-center gap-3">
					<Operator />
					<HourPicker />
				</div>
			</div>
			<nav
				aria-label="Pages"
				className="-mx-4 flex gap-1 overflow-x-auto px-4 sm:-mx-8 sm:px-8 lg:hidden"
			>
				{PLACES.map(({ to, label }) => (
					<NavLink
						key={to}
						to={to}
						end={to === "/"}
						className={({ isActive }) =>
							`flex h-10 shrink-0 items-center rounded-full px-3.5 text-[14px] ${isActive ? "bg-wash-strong font-bold" : "hover:bg-wash"}`
						}
					>
						{label}
					</NavLink>
				))}
			</nav>
		</header>
	);
}
