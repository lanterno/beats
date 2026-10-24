/**
 * Organisation Domain Types (docs/organisations.md).
 *
 * An organisation is a party that owns projects and reads the hours on
 * them. A person has one account and one timeline; joining an organisation
 * adds a membership, never a second account. What the organisation sees is
 * `Record`: finished entries on its own projects (start, end, hours, the
 * note), absences (date, type, half day), totals, and a contract's balance
 * — nothing about now, and nothing personal.
 */

import type { ProjectKind } from "@/entities/project";

export type OrgRole = "owner" | "admin" | "member";

export type WeekStart = "monday" | "saturday" | "sunday";

export interface Organisation {
	id: string;
	name: string;
	logoUrl?: string;
	weekStart: WeekStart;
	holidayCountry?: string;
	holidaySubdivision?: string;
	timezone: string;
	createdAt: string;
}

/** What an organisation is set up with: the fields its admins write. */
export interface OrganisationInput {
	name: string;
	logoUrl?: string;
	weekStart: WeekStart;
	holidayCountry?: string;
	holidaySubdivision?: string;
	timezone: string;
}

export type MembershipEnd = "left" | "removed" | "erased";

/** One of the caller's organisations, with their standing in it. */
export interface Membership {
	organisation: Organisation;
	role: OrgRole;
	joinedAt: string;
	/** Set once the membership has ended; the archive is reached through it. */
	leftAt?: string;
	leftReason?: MembershipEnd;
}

/** A member as the organisation lists them. */
export interface Member {
	userId: string;
	name: string;
	email: string;
	role: OrgRole;
	joinedAt: string;
	leftAt?: string;
}

/** An invitation to one address, or with no email an invite link. */
export interface Invite {
	id: string;
	email?: string;
	role: OrgRole;
	requiresApproval: boolean;
	token: string;
	createdAt: string;
	expiresAt: string;
	acceptedAt?: string;
}

export interface InviteInput {
	email?: string;
	role: OrgRole;
	requiresApproval: boolean;
	expiresInDays: number;
}

/** The organisation as a joiner sees it before joining. */
export interface OrganisationCard {
	id: string;
	name: string;
	logoUrl?: string;
}

/** An open invitation addressed to the caller's own address. */
export interface Invitation {
	token: string;
	role: OrgRole;
	expiresAt: string;
	organisation: OrganisationCard;
}

export interface InvitePreview {
	organisation: OrganisationCard;
	role: OrgRole;
	requiresApproval: boolean;
	/** To the caller's address, as opposed to a link anyone may use. */
	addressed: boolean;
	alreadyMember: boolean;
}

export type JoinResult =
	| { status: "joined"; membership: Membership }
	| { status: "pending"; membership?: undefined };

export interface JoinRequest {
	id: string;
	userId: string;
	name: string;
	email: string;
	requestedAt: string;
}

/** One member on one of the organisation's projects. */
export interface Assignment {
	userId: string;
	name?: string;
	/** The instant from which the member's hours on the project are the organisation's. */
	sharedFrom: string;
	assignedAt: string;
	endedAt?: string;
	hasContract: boolean;
}

/** An organisation's project as the organisation sees it, with who is on it. */
export interface OrgProject {
	id: string;
	name: string;
	description?: string;
	color?: string;
	archived: boolean;
	kind: ProjectKind;
	githubRepo?: string;
	category?: string;
	members: Assignment[];
}

/** The organisation's fields of one of its projects. */
export interface OrgProjectInput {
	name: string;
	description?: string;
	color?: string;
	kind: ProjectKind;
	githubRepo?: string;
	category?: string;
	archived: boolean;
}

/** One finished entry as the organisation reads it. */
export interface RecordEntry {
	id: string;
	day: string; // YYYY-MM-DD, the local day it started on
	start: string; // ISO datetime
	end: string; // ISO datetime
	hours: number;
	note?: string;
}

export interface RecordAbsence {
	date: string;
	type: string;
	halfDay: boolean;
}

export interface MemberBalance {
	asOf: string;
	balance: number;
	opening: number;
	worked: number;
	expectedThrough: number;
	adjusted: number;
}

export interface MemberTotals {
	entries: number;
	hours: number;
	first?: string;
	last?: string;
}

/** One member's slice of one project, as the organisation reads it. */
export interface MemberRecord {
	userId: string;
	name: string;
	sharedFrom: string;
	/** Still assigned; false once they left the project or the organisation. */
	active: boolean;
	/** The month's hours. */
	hours: number;
	entries: RecordEntry[];
	absences: RecordAbsence[];
	hasContract: boolean;
	balance?: MemberBalance;
	totals: MemberTotals;
}

export interface ProjectRecord {
	project: Omit<OrgProject, "members">;
	members: MemberRecord[];
}

/**
 * What the organisation sees in a month — and, read through `/visible`,
 * what it sees of one member: the same shape from the same read.
 */
export interface OrgRecord {
	organisation: OrganisationCard;
	month: string; // YYYY-MM
	first: string;
	last: string;
	projects: ProjectRecord[];
}

export interface ArchiveProject {
	projectId: string;
	name: string;
	color?: string;
	hours: number;
	entries: RecordEntry[];
}

/** The person's own hours that are one organisation's record, by project. */
export interface Archive {
	organisation: OrganisationCard;
	role: OrgRole;
	joinedAt: string;
	leftAt?: string;
	hours: number;
	projects: ArchiveProject[];
}
