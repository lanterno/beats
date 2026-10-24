/**
 * The small rules the organisation pages share: which role may do what,
 * what the roles and week starts are called, how an invite becomes a URL,
 * and how a connected project's `sharedFrom` reads.
 */

import { formatDateShort, parseUtcIso } from "@/shared/lib";
import type { OrgRole, WeekStart } from "./types";

const RANK: Record<OrgRole, number> = { member: 0, admin: 1, owner: 2 };

export function roleAtLeast(role: OrgRole, needed: OrgRole): boolean {
	return RANK[role] >= RANK[needed];
}

/** Whether a role sees the organisation's members, projects, invites and record. */
export function canAdminister(role: OrgRole): boolean {
	return roleAtLeast(role, "admin");
}

export const ROLE_LABELS: Record<OrgRole, string> = {
	owner: "Owner",
	admin: "Admin",
	member: "Member",
};

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
