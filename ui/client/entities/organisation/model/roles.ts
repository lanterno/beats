/**
 * The small rules the organisation pages share: which role may do what,
 * what the roles and week starts are called, how an invite becomes a URL,
 * and how a connected project's `sharedFrom` reads.
 */

import { formatDateShort, parseUtcIso } from "@/shared/lib";
import type { OrgRole, WeekStart } from "./types";

const RANK: Record<OrgRole, number> = { member: 0, viewer: 1, manager: 2, admin: 3, owner: 4 };

function roleAtLeast(role: OrgRole, needed: OrgRole): boolean {
	return RANK[role] >= RANK[needed];
}

/** Whether a role runs the organisation: members, projects, invites, settings. */
export function canAdminister(role: OrgRole): boolean {
	return roleAtLeast(role, "admin");
}

export const ROLE_LABELS: Record<OrgRole, string> = {
	owner: "Owner",
	admin: "Admin",
	manager: "Manager",
	viewer: "Viewer",
	member: "Member",
};

/** What each role is for, where one is picked. */
export const ROLE_HINTS: Record<OrgRole, string> = {
	owner: "Runs the organisation; the last one stays",
	admin: "Members, projects, invites and settings",
	manager: "Decides absences and timesheets for their teams",
	viewer: "Reads the record; changes nothing",
	member: "Tracks on assigned projects",
};

/** Whether a role decides absence requests and timesheets (a manager: their teams'). */
export function decides(role: OrgRole): boolean {
	return role === "owner" || role === "admin" || role === "manager";
}

/** Whether a role reads the record at all. */
export function readsRecord(role: OrgRole): boolean {
	return role !== "member";
}

export const WEEK_START_LABELS: Record<WeekStart, string> = {
	monday: "Monday",
	saturday: "Saturday",
	sunday: "Sunday",
};

/** The URL a joiner opens: the join page, on this origin, with the token. */
export function inviteUrl(token: string, origin: string = window.location.origin): string {
	return `${origin}/organisations/join/${encodeURIComponent(token)}`;
}

/**
 * "since Mar 4, 2026" — the day the member's hours on a project became the
 * organisation's, in the reader's own zone. `sharedFrom` is an instant,
 * local midnight of the day they chose when they connected the project, or
 * the moment of assignment.
 */
export function describeShareFrom(sharedFrom: string): string {
	const d = parseUtcIso(sharedFrom);
	return `since ${formatDateShort(d)}, ${d.getFullYear()}`;
}
