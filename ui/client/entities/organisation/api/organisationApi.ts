/**
 * Organisation API Functions — /api/organisations (docs/organisations.md).
 * Outside every device-token prefix: a paired device tracks on an
 * organisation's project through /api/projects like any other, and reaches
 * nothing here.
 */

import {
	ApiArchiveSchema,
	ApiAssignmentSchema,
	ApiInvitationListSchema,
	ApiInviteListSchema,
	ApiInvitePreviewSchema,
	ApiInviteSchema,
	ApiJoinRequestListSchema,
	ApiJoinRequestSchema,
	ApiJoinSchema,
	ApiMemberListSchema,
	ApiMemberSchema,
	ApiMembershipListSchema,
	ApiMembershipSchema,
	ApiOrganisationSchema,
	ApiOrgProjectListSchema,
	ApiOrgProjectSchema,
	ApiRecordSchema,
	del,
	get,
	parseApiResponse,
	patch,
	post,
	put,
} from "@/shared/api";
import { browserTimeZone } from "@/shared/lib";
import type {
	Archive,
	Assignment,
	Invitation,
	Invite,
	InviteInput,
	InvitePreview,
	JoinRequest,
	JoinResult,
	Member,
	Membership,
	Organisation,
	OrganisationInput,
	OrgProject,
	OrgProjectInput,
	OrgRecord,
	OrgRole,
} from "../model";
import {
	toApiInviteInput,
	toApiOrganisationInput,
	toApiOrgProjectInput,
	toArchive,
	toAssignment,
	toInvitation,
	toInvite,
	toInvitePreview,
	toJoinRequest,
	toJoinResult,
	toMember,
	toMembership,
	toOrganisation,
	toOrgProject,
	toRecord,
} from "../model";

const BASE = "/api/organisations";

/** Every organisation the caller is or was in, with their membership. */
export async function fetchMemberships(): Promise<Membership[]> {
	const data = await get<unknown>(`${BASE}/`);
	return parseApiResponse(ApiMembershipListSchema, data).map(toMembership);
}

export async function createOrganisation(input: OrganisationInput): Promise<Membership> {
	const data = await post<unknown>(`${BASE}/`, toApiOrganisationInput(input));
	return toMembership(parseApiResponse(ApiMembershipSchema, data));
}

export async function fetchMembership(organisationId: string): Promise<Membership> {
	const data = await get<unknown>(`${BASE}/${organisationId}`);
	return toMembership(parseApiResponse(ApiMembershipSchema, data));
}

export async function updateOrganisation(
	organisationId: string,
	input: OrganisationInput,
): Promise<Organisation> {
	const data = await put<unknown>(`${BASE}/${organisationId}`, toApiOrganisationInput(input));
	return toOrganisation(parseApiResponse(ApiOrganisationSchema, data));
}

/** Start the closing notice (#347); null takes the API's default, 60 days. */
export async function beginClosing(
	organisationId: string,
	closesOn: string | null,
): Promise<Organisation> {
	const data = await post<unknown>(`${BASE}/${organisationId}/close`, { closes_on: closesOn });
	return toOrganisation(parseApiResponse(ApiOrganisationSchema, data));
}

export async function cancelClosing(organisationId: string): Promise<Organisation> {
	const data = await del<unknown>(`${BASE}/${organisationId}/close`);
	return toOrganisation(parseApiResponse(ApiOrganisationSchema, data));
}

/** Delete the organisation, once its notice has run out. */
export async function deleteOrganisation(organisationId: string): Promise<void> {
	await del<void>(`${BASE}/${organisationId}`);
}

export async function fetchMembers(organisationId: string): Promise<Member[]> {
	const data = await get<unknown>(`${BASE}/${organisationId}/members`);
	return parseApiResponse(ApiMemberListSchema, data).map(toMember);
}

/** 403 OWNER_ROLE_RESERVED below owner for the owner role; 409 LAST_OWNER for the last one. */
export async function setMemberRole(
	organisationId: string,
	userId: string,
	role: OrgRole,
): Promise<Member> {
	const data = await patch<unknown>(`${BASE}/${organisationId}/members/${userId}`, { role });
	return toMember(parseApiResponse(ApiMemberSchema, data));
}

export async function removeMember(organisationId: string, userId: string): Promise<void> {
	await del<void>(`${BASE}/${organisationId}/members/${userId}`);
}

/** 409 LAST_OWNER for the only owner. */
export async function leaveOrganisation(organisationId: string): Promise<Membership> {
	const data = await post<unknown>(`${BASE}/${organisationId}/leave`);
	return toMembership(parseApiResponse(ApiMembershipSchema, data));
}

export async function createInvite(organisationId: string, input: InviteInput): Promise<Invite> {
	const data = await post<unknown>(`${BASE}/${organisationId}/invites`, toApiInviteInput(input));
	return toInvite(parseApiResponse(ApiInviteSchema, data));
}

export async function fetchInvites(organisationId: string): Promise<Invite[]> {
	const data = await get<unknown>(`${BASE}/${organisationId}/invites`);
	return parseApiResponse(ApiInviteListSchema, data).map(toInvite);
}

export async function revokeInvite(organisationId: string, inviteId: string): Promise<void> {
	await del<void>(`${BASE}/${organisationId}/invites/${inviteId}`);
}

/** The open invitations addressed to the caller's own address. */
export async function fetchInvitations(): Promise<Invitation[]> {
	const data = await get<unknown>(`${BASE}/invitations`);
	return parseApiResponse(ApiInvitationListSchema, data).map(toInvitation);
}

/**
 * 404 INVITE_NOT_FOUND for an unknown token or another's; 410 INVITE_EXPIRED
 * for a closed one. The token rides X-Invite-Token rather than the URL (and
 * the body on join): request logs keep URLs, and an unused invitation is a
 * standing way in. The /join/<token> link people share is the SPA's route.
 */
export async function fetchInvitePreview(token: string): Promise<InvitePreview> {
	const data = await get<unknown>(`${BASE}/join`, { "X-Invite-Token": token });
	return toInvitePreview(parseApiResponse(ApiInvitePreviewSchema, data));
}

/** 409 ALREADY_A_MEMBER, or JOIN_REQUEST_PENDING while a request waits. */
export async function joinOrganisation(token: string): Promise<JoinResult> {
	const data = await post<unknown>(`${BASE}/join`, { token });
	return toJoinResult(parseApiResponse(ApiJoinSchema, data));
}

export async function fetchJoinRequests(organisationId: string): Promise<JoinRequest[]> {
	const data = await get<unknown>(`${BASE}/${organisationId}/requests`);
	return parseApiResponse(ApiJoinRequestListSchema, data).map(toJoinRequest);
}

export async function decideJoinRequest(
	organisationId: string,
	requestId: string,
	decision: "approved" | "declined",
): Promise<JoinRequest> {
	const data = await post<unknown>(`${BASE}/${organisationId}/requests/${requestId}`, {
		decision,
	});
	return toJoinRequest(parseApiResponse(ApiJoinRequestSchema, data));
}

export async function fetchOrgProjects(organisationId: string): Promise<OrgProject[]> {
	const data = await get<unknown>(`${BASE}/${organisationId}/projects`);
	return parseApiResponse(ApiOrgProjectListSchema, data).map(toOrgProject);
}

export async function createOrgProject(
	organisationId: string,
	input: OrgProjectInput,
): Promise<OrgProject> {
	const data = await post<unknown>(
		`${BASE}/${organisationId}/projects`,
		toApiOrgProjectInput(input),
	);
	return toOrgProject(parseApiResponse(ApiOrgProjectSchema, data));
}

export async function updateOrgProject(
	organisationId: string,
	projectId: string,
	input: OrgProjectInput,
): Promise<OrgProject> {
	const data = await put<unknown>(
		`${BASE}/${organisationId}/projects/${projectId}`,
		toApiOrgProjectInput(input),
	);
	return toOrgProject(parseApiResponse(ApiOrgProjectSchema, data));
}

/** Fold one of the organisation's projects into another (decision 28). */
export async function mergeOrgProject(
	organisationId: string,
	projectId: string,
	into: string,
): Promise<OrgProject> {
	const data = await post<unknown>(`${BASE}/${organisationId}/projects/${projectId}/merge`, {
		into,
	});
	return toOrgProject(parseApiResponse(ApiOrgProjectSchema, data));
}

export async function assignMember(
	organisationId: string,
	projectId: string,
	userId: string,
): Promise<Assignment> {
	const data = await put<unknown>(
		`${BASE}/${organisationId}/projects/${projectId}/members/${userId}`,
		{},
	);
	return toAssignment(parseApiResponse(ApiAssignmentSchema, data));
}

export async function unassignMember(
	organisationId: string,
	projectId: string,
	userId: string,
): Promise<void> {
	await del<void>(`${BASE}/${organisationId}/projects/${projectId}/members/${userId}`);
}

/**
 * Connect one of the caller's own projects: from `shareFrom` (a local day,
 * YYYY-MM-DD, in the browser's zone) the hours and absences on it are the
 * organisation's; null starts fresh from now. 409 PROJECT_HAS_BILLING on a
 * billed project, ORGANISATION_PROJECT on one already an organisation's,
 * SHARE_FROM_IN_FUTURE for a day after today.
 */
export async function connectProject(
	organisationId: string,
	projectId: string,
	shareFrom: string | null,
): Promise<Assignment> {
	const params = new URLSearchParams({ tz: browserTimeZone() });
	const data = await post<unknown>(`${BASE}/${organisationId}/connect?${params.toString()}`, {
		project_id: projectId,
		share_from: shareFrom,
	});
	return toAssignment(parseApiResponse(ApiAssignmentSchema, data));
}

function monthParams(month: string): string {
	return new URLSearchParams({ month, tz: browserTimeZone() }).toString();
}

/** What the organisation sees in `month` (YYYY-MM). Admins. */
export async function fetchRecord(organisationId: string, month: string): Promise<OrgRecord> {
	const data = await get<unknown>(`${BASE}/${organisationId}/record?${monthParams(month)}`);
	return toRecord(parseApiResponse(ApiRecordSchema, data));
}

/** What the organisation sees of the caller in `month` — the same read, narrowed. */
export async function fetchVisible(organisationId: string, month: string): Promise<OrgRecord> {
	const data = await get<unknown>(`${BASE}/${organisationId}/visible?${monthParams(month)}`);
	return toRecord(parseApiResponse(ApiRecordSchema, data));
}

/** The caller's own hours that are this organisation's record. */
export async function fetchArchive(organisationId: string): Promise<Archive> {
	const params = new URLSearchParams({ tz: browserTimeZone() });
	const data = await get<unknown>(`${BASE}/${organisationId}/archive?${params.toString()}`);
	return toArchive(parseApiResponse(ApiArchiveSchema, data));
}

/** Where the archive's CSV is, for `downloadFile`. */
export function archiveCsvUrl(organisationId: string): string {
	const params = new URLSearchParams({ tz: browserTimeZone() });
	return `${BASE}/${organisationId}/archive.csv?${params.toString()}`;
}

// --- Employment (docs/organisations.md, stages 3 and 4) -----------------------

import type { ApiContract } from "@/shared/api";
import {
	ApiAbsenceRequestListSchema,
	ApiAbsenceRequestSchema,
	ApiAuditEventListSchema,
	ApiManagedContractSchema,
	ApiTeamListSchema,
	ApiTeamSchema,
	ApiTimesheetListSchema,
	ApiTimesheetSchema,
} from "@/shared/api";
import type {
	AbsenceRequest,
	AuditEvent,
	ManagedContract,
	Team,
	TeamInput,
	Timesheet,
} from "../model";
import {
	toAbsenceRequest,
	toApiTeamInput,
	toAuditEvent,
	toManagedContract,
	toTeam,
	toTimesheet,
} from "../model";

export async function fetchTeams(organisationId: string): Promise<Team[]> {
	const data = await get<unknown>(`${BASE}/${organisationId}/teams`);
	return parseApiResponse(ApiTeamListSchema, data).map(toTeam);
}

export async function createTeam(organisationId: string, input: TeamInput): Promise<Team> {
	const data = await post<unknown>(`${BASE}/${organisationId}/teams`, toApiTeamInput(input));
	return toTeam(parseApiResponse(ApiTeamSchema, data));
}

export async function updateTeam(
	organisationId: string,
	teamId: string,
	input: TeamInput,
): Promise<Team> {
	const data = await put<unknown>(
		`${BASE}/${organisationId}/teams/${teamId}`,
		toApiTeamInput(input),
	);
	return toTeam(parseApiResponse(ApiTeamSchema, data));
}

export async function deleteTeam(organisationId: string, teamId: string): Promise<void> {
	await del<void>(`${BASE}/${organisationId}/teams/${teamId}`);
}

export async function fetchManagedContract(
	organisationId: string,
	projectId: string,
	userId: string,
): Promise<ManagedContract> {
	const data = await get<unknown>(
		`${BASE}/${organisationId}/projects/${projectId}/members/${userId}/contract`,
	);
	return toManagedContract(parseApiResponse(ApiManagedContractSchema, data));
}

/** The wire contract comes from the project entity's `toApiContract`. */
export async function setManagedContract(
	organisationId: string,
	projectId: string,
	userId: string,
	contract: ApiContract | null,
	managed: boolean,
): Promise<ManagedContract> {
	const data = await put<unknown>(
		`${BASE}/${organisationId}/projects/${projectId}/members/${userId}/contract`,
		{ contract, managed },
	);
	return toManagedContract(parseApiResponse(ApiManagedContractSchema, data));
}

export async function enterTime(
	organisationId: string,
	projectId: string,
	userId: string,
	input: { start: string; end: string; note?: string },
): Promise<void> {
	await post<unknown>(`${BASE}/${organisationId}/projects/${projectId}/members/${userId}/entries`, {
		start: input.start,
		end: input.end,
		note: input.note ?? null,
	});
}

export async function requestAbsence(
	organisationId: string,
	input: {
		projectId: string;
		date: string;
		type: "vacation" | "sick" | "other";
		halfDay: boolean;
		note?: string;
	},
): Promise<AbsenceRequest> {
	const data = await post<unknown>(`${BASE}/${organisationId}/absence-requests`, {
		project_id: input.projectId,
		date: input.date,
		type: input.type,
		half_day: input.halfDay,
		note: input.note ?? null,
	});
	return toAbsenceRequest(parseApiResponse(ApiAbsenceRequestSchema, data));
}

export async function fetchAbsenceRequests(
	organisationId: string,
	pending = false,
): Promise<AbsenceRequest[]> {
	const data = await get<unknown>(`${BASE}/${organisationId}/absence-requests?pending=${pending}`);
	return parseApiResponse(ApiAbsenceRequestListSchema, data).map(toAbsenceRequest);
}

export async function decideAbsenceRequest(
	organisationId: string,
	requestId: string,
	approve: boolean,
	comment?: string,
): Promise<AbsenceRequest> {
	const data = await post<unknown>(
		`${BASE}/${organisationId}/absence-requests/${requestId}/decision`,
		{ approve, comment: comment ?? null },
	);
	return toAbsenceRequest(parseApiResponse(ApiAbsenceRequestSchema, data));
}

export async function withdrawAbsenceRequest(
	organisationId: string,
	requestId: string,
): Promise<void> {
	await del<void>(`${BASE}/${organisationId}/absence-requests/${requestId}`);
}

export async function submitTimesheet(
	organisationId: string,
	projectId: string,
	month: string, // "YYYY-MM" or any day of the month
): Promise<Timesheet> {
	const data = await post<unknown>(`${BASE}/${organisationId}/timesheets`, {
		project_id: projectId,
		// The API stores the 1st whatever day is sent; normalise here so a
		// caller may pass "2026-09" or "2026-09-01" alike.
		month: `${month.slice(0, 7)}-01`,
	});
	return toTimesheet(parseApiResponse(ApiTimesheetSchema, data));
}

export async function fetchTimesheets(
	organisationId: string,
	month?: string, // YYYY-MM
): Promise<Timesheet[]> {
	const params = month ? `?month=${month}` : "";
	const data = await get<unknown>(`${BASE}/${organisationId}/timesheets${params}`);
	return parseApiResponse(ApiTimesheetListSchema, data).map(toTimesheet);
}

export async function decideTimesheet(
	organisationId: string,
	sheetId: string,
	approve: boolean,
	comment?: string,
): Promise<Timesheet> {
	const data = await post<unknown>(`${BASE}/${organisationId}/timesheets/${sheetId}/decision`, {
		approve,
		comment: comment ?? null,
	});
	return toTimesheet(parseApiResponse(ApiTimesheetSchema, data));
}

export async function reopenTimesheet(
	organisationId: string,
	sheetId: string,
	reason: string,
): Promise<Timesheet> {
	const data = await post<unknown>(`${BASE}/${organisationId}/timesheets/${sheetId}/reopen`, {
		reason,
	});
	return toTimesheet(parseApiResponse(ApiTimesheetSchema, data));
}

export async function fetchAuditLog(
	organisationId: string,
	before?: string,
): Promise<AuditEvent[]> {
	const params = before ? `?before=${encodeURIComponent(before)}` : "";
	const data = await get<unknown>(`${BASE}/${organisationId}/audit${params}`);
	return parseApiResponse(ApiAuditEventListSchema, data).map(toAuditEvent);
}

/** Where the month's record and compliance CSVs are, for `downloadFile`. */
export function recordCsvUrl(organisationId: string, month: string): string {
	const params = new URLSearchParams({ month, tz: browserTimeZone() });
	return `${BASE}/${organisationId}/record.csv?${params.toString()}`;
}

export function complianceCsvUrl(organisationId: string, month: string): string {
	const params = new URLSearchParams({ month, tz: browserTimeZone() });
	return `${BASE}/${organisationId}/compliance.csv?${params.toString()}`;
}

/** The caller's own visible month as CSV: what is seen of them, to take away. */
export function visibleCsvUrl(organisationId: string, month: string): string {
	const params = new URLSearchParams({ month, tz: browserTimeZone() });
	return `${BASE}/${organisationId}/visible.csv?${params.toString()}`;
}
