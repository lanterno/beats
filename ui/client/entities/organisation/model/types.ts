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

export type OrgRole = "owner" | "admin" | "manager" | "viewer" | "member";

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
	/** The caller's own id: which member row, or which timesheet, is theirs. */
	userId: string;
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

/**
 * An open invitation addressed to the caller's own address: who, and as
 * what. Not the token — the way in is the link the inviter passed on.
 */
export interface Invitation {
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
	/** What approving grants: the invite's role. */
	role: OrgRole;
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
	projects: ProjectRecord[];
}

export interface ArchiveProject {
	projectId: string;
	name: string;
	color?: string;
	hours: number;
	entries: RecordEntry[];
	absences: RecordAbsence[];
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

// Employment (docs/organisations.md, stages 3 and 4).

/** A team: a name and who is in it — what gives a manager their scope. */
export interface Team {
	id: string;
	name: string;
	memberIds: string[];
}

export interface TeamInput {
	name: string;
	memberIds: string[];
}

export type RequestStatus = "pending" | "approved" | "declined";

/** A day off asked for on a managed assignment, and what became of it. */
export interface AbsenceRequest {
	id: string;
	projectId: string;
	/** The names come with the row: a decider may not list the projects. */
	projectName?: string;
	userId: string;
	memberName?: string;
	date: string;
	type: "vacation" | "sick" | "other";
	halfDay: boolean;
	note?: string;
	status: RequestStatus;
	requestedAt: string;
	decidedAt?: string;
	decidedBy?: string;
	decidedByName?: string;
	comment?: string;
}

export type TimesheetStatus = "submitted" | "approved" | "changes_requested" | "reopened";

/** What approval froze: the month's figures as they stood. */
export interface FrozenMonth {
	worked: number;
	expected: number | null;
	balanceEnd: number | null;
	entries: number;
	absenceDays: number;
}

export interface TimesheetEvent {
	at: string;
	by: string;
	action: TimesheetStatus;
	comment?: string;
}

/** One member's month on one organisation project, submitted and decided. */
export interface Timesheet {
	id: string;
	projectId: string;
	/** As on `AbsenceRequest`: the row names itself. */
	projectName?: string;
	userId: string;
	memberName?: string;
	month: string; // YYYY-MM-01
	status: TimesheetStatus;
	submittedAt: string;
	decidedAt?: string;
	decidedBy?: string;
	decidedByName?: string;
	comment?: string;
	frozen?: FrozenMonth;
	history: TimesheetEvent[];
}

/** The employer's view of one assignment's contract. */
export interface ManagedContract {
	projectId: string;
	userId: string;
	managed: boolean;
	/** The wire contract, passed to the project entity's mappers where edited. */
	contract: unknown | null;
}

/** One line of the audit log. */
export interface AuditEvent {
	at: string;
	actorUserId?: string;
	event: string;
	subjectUserId?: string;
	projectId?: string;
	details: Record<string, unknown>;
}
