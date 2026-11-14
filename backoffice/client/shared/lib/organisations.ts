/**
 * The organisation pages' rules, apart from the pages so they can be tested:
 * where an organisation stands, what its sentence says, and how its counts
 * read. The API answers counts by role, states and dates
 * (`GET /api/operator/organisations`, `/organisations/{id}`); every word
 * here is the control plane's own, and nothing here decides what the
 * operator may do — the runner refuses an act the moment an owner exists.
 */

import type { OrganisationSummary } from "@/shared/api/schema";
import { counted } from "@/shared/lib/format";

/** Which filter an organisation falls under on the list. */
export type OrgGroup = "needs" | "leaving" | "active";

export type Tone = "quiet" | "good" | "owed" | "warn";

/** A queued `organisation.delete`, as the job queue holds it. */
export interface Deletion {
	id: string;
	run_after: string;
}

export interface Standing {
	group: OrgGroup;
	ownership: { label: string; tone: Tone };
	state: { label: string; tone: Tone };
}

type Job = Record<string, unknown>;

/** The deletion waiting for this organisation, if one is queued. */
export function deletionOf(jobs: readonly Job[], organisationId: string): Deletion | null {
	const job = jobs.find(
		(j) =>
			j.command === "organisation.delete" &&
			j.subject_id === organisationId &&
			(j.state === "queued" || j.state === "running"),
	);
	return job && typeof job.id === "string"
		? { id: job.id, run_after: typeof job.run_after === "string" ? job.run_after : "" }
		: null;
}

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

/** "Deleting in 18 h", or "Deleting now" once its window has ended and the
 * job runner has yet to take it. */
function deletingIn(deletion: Deletion, now: Date): string {
	const left = Date.parse(deletion.run_after) - now.getTime();
	return left > 0 ? `Deleting in ${Math.ceil(left / HOUR)} h` : "Deleting now";
}

/**
 * Where an organisation stands. One with no owner needs you, until a closing
 * or a deletion is under way, which is the operator having acted already;
 * one whose every owner is suspended is watched, not acted on — a suspended
 * owner is still its owner.
 */
export function standing(o: OrganisationSummary, deletion: Deletion | null, now: Date): Standing {
	const ownership =
		o.owners === 0 ? "No owner" : o.all_owners_suspended ? "Every owner suspended" : "Has an owner";
	if (deletion) {
		return {
			group: "leaving",
			ownership: { label: ownership, tone: "quiet" },
			state: { label: deletingIn(deletion, now), tone: "warn" },
		};
	}
	if (o.closes_on) {
		return {
			group: "leaving",
			ownership: { label: ownership, tone: "quiet" },
			state: { label: `Closing ${o.closes_on}`, tone: "quiet" },
		};
	}
	if (o.owners === 0) {
		return {
			group: "needs",
			ownership: { label: ownership, tone: "owed" },
			state: { label: "Needs you", tone: "owed" },
		};
	}
	if (o.all_owners_suspended) {
		return {
			group: "needs",
			ownership: { label: ownership, tone: "warn" },
			state: { label: "Watching", tone: "warn" },
		};
	}
	return {
		group: "active",
		ownership: { label: ownership, tone: "quiet" },
		state: { label: "Active", tone: "good" },
	};
}

const WAITING = ["No organisation is", "One organisation is", "Two organisations are"];

/** The list's sentence: how many have nobody left to act, and are not yet
 * closing or being deleted. */
export function organisationsHeadline(standings: readonly Standing[]): string {
	const n = standings.filter((s) => s.state.label === "Needs you").length;
	return `${WAITING[n] ?? `${n} organisations are`} waiting for you.`;
}

/** One organisation's sentence, for its page. */
export function organisationHeadline(o: OrganisationSummary, deletion: Deletion | null): string {
	if (deletion) return `${o.name} is queued for deletion.`;
	if (o.owners === 0) return `${o.name} has no owner.`;
	if (o.all_owners_suspended) return `Every owner of ${o.name} is suspended.`;
	if (o.closes_on) return `${o.name} closes on ${o.closes_on}.`;
	return `${o.name} has an owner, and runs itself.`;
}

/** The ladder, highest first (OrgRole in api/src/beats/domain/models_organisations.py). */
const LADDER = ["owner", "admin", "manager", "viewer", "member"];

const capital = (word: string): string => word.charAt(0).toUpperCase() + word.slice(1);

/** Everyone with a membership not ended, whatever their role. */
export function memberCount(byRole: Record<string, number> | undefined): number {
	return Object.values(byRole ?? {}).reduce((sum, n) => sum + n, 0);
}

/** "Admin, 2 people": the highest role anyone active holds, and how many
 * hold it. Read off the ladder, not off the order the API listed them in. */
export function highestRole(byRole: Record<string, number> | undefined): string {
	const top = LADDER.find((role) => (byRole?.[role] ?? 0) > 0);
	if (!top) return "Nobody";
	return `${capital(top)}, ${counted(byRole?.[top] ?? 0, "person", "people")}`;
}

/** The roles anyone active holds, highest first, each with how many. */
export function rolesOnLadder(byRole: Record<string, number> | undefined): Array<[string, number]> {
	return LADDER.filter((role) => (byRole?.[role] ?? 0) > 0).map((role) => [
		capital(role),
		byRole?.[role] ?? 0,
	]);
}

/** "3 years", "1 year", or the platform's default when it set none. */
export function keepsFor(years: number | null | undefined): string {
	return years ? counted(years, "year", "years") : "The default";
}

/**
 * Whether a deletion queued now would find its closing day come when it
 * runs, a day later. Read in UTC; the job checks the day in the
 * organisation's own timezone when it runs, and refuses it if the day has
 * not come there, so this only keeps the link off a page where it cannot
 * succeed.
 */
export function deletionReady(closesOn: string | null | undefined, now: Date): boolean {
	if (!closesOn) return false;
	return closesOn <= new Date(now.getTime() + DAY).toISOString().slice(0, 10);
}

/** "3", "3, 1 brought in by a member", or "None". A project is brought in
 * when a member connects their own; the rest the organisation made. */
export function projectsFact(total: number, broughtIn: number): string {
	if (total === 0) return "None";
	if (broughtIn === 0) return String(total);
	return `${total}, ${broughtIn} brought in by ${broughtIn === 1 ? "a member" : "members"}`;
}

/** "3 open, 5 submitted, 120 approved", or "None". */
export function timesheets(byStatus: Record<string, number> | undefined): string {
	const entries = Object.entries(byStatus ?? {}).filter(([, n]) => n > 0);
	return entries.length ? entries.map(([status, n]) => `${n} ${status}`).join(", ") : "None";
}

/** An audit event's name in words: "member.role_changed" → "Member role
 * changed". The name is the API's; nothing it carries is read. */
export function eventWords(event: string): string {
	const words = event.replace(/[._]/g, " ").trim();
	return words ? capital(words) : "—";
}
