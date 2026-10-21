/**
 * ReportLinkRow — one report link as its maker reads it: its label (the
 * maker's own), its days, what it shows, its projects, the zone its days are
 * counted in, and the last day it opens or that it has ended. Under it, the
 * client's billed projects it leaves out, so a project billed since the link
 * was made is not taken to be on it. The Clients page and Settings both draw
 * links with it; each brings its own actions (Preview, Replace, Turn off,
 * Remove).
 */

import type { ReactNode } from "react";
import { cn, parseIsoDate } from "@/shared/lib";
import { describeShows, type ReportLink } from "../model";

export interface ReportLinkRowProps {
	link: ReportLink;
	/** The client's name, where the list holds more than one client's links. */
	clientName?: string;
	/** The client's billed projects the link leaves out, by name (`notOnLink`). */
	leftOut?: readonly string[];
	/** Under the row: Preview, Replace…, Turn off or Remove. */
	actions?: ReactNode;
	className?: string;
}

/** "15 Sep 2026", day first, as the report the client reads. */
function day(iso: string): string {
	const d = parseIsoDate(iso);
	if (!d) return iso;
	return `${d.getDate()} ${d.toLocaleDateString("en-US", { month: "short" })} ${d.getFullYear()}`;
}

/** "15 Sep – 31 Oct 2026", "15 Dec 2025 – 31 Jan 2026", or the one day. */
function days(first: string, last: string): string {
	if (first === last) return day(first);
	if (first.slice(0, 4) !== last.slice(0, 4)) return `${day(first)} – ${day(last)}`;
	return `${day(first).slice(0, -5)} – ${day(last)}`;
}

export function ReportLinkRow({
	link,
	clientName,
	leftOut,
	actions,
	className,
}: ReportLinkRowProps) {
	const ended = link.state === "ended";
	return (
		<div className={cn("min-w-0 text-[12.5px]", className)}>
			<div className="flex items-center gap-x-2 gap-y-0.5 flex-wrap">
				<span className="font-bold text-foreground min-w-0 break-words">
					{link.label ?? "Untitled link"}
				</span>
				{clientName && <span className="font-medium text-muted-foreground">{clientName}</span>}
				{ended ? (
					<span className="font-body text-[9.5px] font-bold tracking-[0.1em] uppercase px-[9px] py-0.5 rounded-full bg-tint-other text-tint-other-ink">
						Ended
					</span>
				) : (
					<span className="font-medium text-muted-foreground">
						Works until{" "}
						<span className="font-mono font-bold text-foreground">{day(link.expiresOn)}</span>
					</span>
				)}
			</div>
			<p className="mt-0.5 font-medium text-muted-foreground leading-normal">
				<span className="font-mono font-bold text-foreground">{days(link.first, link.last)}</span>
				{" · "}
				{describeShows(link)}
				{" · "}
				{link.projects.length > 0
					? link.projects.map((project) => project.name).join(", ")
					: "No projects left on this link"}
				{" · "}
				Days in {link.tz}
			</p>
			{leftOut && leftOut.length > 0 && (
				<p className="mt-0.5 font-medium text-muted-foreground">
					Not on this link: {leftOut.join(", ")}
				</p>
			)}
			{actions && <div className="mt-1.5 flex items-center gap-3 flex-wrap">{actions}</div>}
		</div>
	);
}
