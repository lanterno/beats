/**
 * The desktop frame's left column: the mark, then the places in their
 * groups. Translucent over the sky, as the app's sidebar is; what tells it
 * apart from the app is the "Back office" pill under the name, which the
 * topbar repeats at every width.
 */

import { NavLink } from "react-router";
import { APP_NAME } from "@/shared/config/brand";
import { BrandMark } from "@/shared/ui/icons";
import { GROUPS, type Place } from "./places";

export function BackOfficeMark({ className = "" }: { className?: string }) {
	return (
		<span
			className={`rounded-full bg-ink px-2 py-0.5 text-[12px] leading-tight font-bold whitespace-nowrap text-panel-solid ${className}`}
		>
			Back office
		</span>
	);
}

function PlaceLink({ place }: { place: Place }) {
	const { to, label, Icon } = place;
	return (
		<NavLink
			to={to}
			end={to === "/"}
			className={({ isActive }) =>
				`flex h-10 items-center gap-2.5 rounded-full px-3.5 text-[14px] ${isActive ? "bg-wash-strong font-bold" : "hover:bg-wash"}`
			}
		>
			<Icon />
			{label}
		</NavLink>
	);
}

export function Sidebar() {
	return (
		<aside className="sticky top-0 hidden h-screen w-[236px] shrink-0 flex-col gap-6 bg-sidebar px-3 py-5 lg:flex">
			<div className="flex items-center gap-2.5 px-2">
				<BrandMark className="size-10 shrink-0" />
				<div className="flex flex-col items-start gap-1">
					<span className="font-heading text-[17px] leading-none font-extrabold">{APP_NAME}</span>
					<BackOfficeMark />
				</div>
			</div>
			<nav aria-label="Pages" className="flex flex-col gap-4">
				{GROUPS.map((group) => (
					<div key={group.label ?? "today"} className="flex flex-col gap-0.5">
						{group.label ? (
							<p className="px-3.5 pb-1 text-[13px] text-ink-muted">{group.label}</p>
						) : null}
						{group.places.map((place) => (
							<PlaceLink key={place.to} place={place} />
						))}
					</div>
				))}
			</nav>
		</aside>
	);
}
