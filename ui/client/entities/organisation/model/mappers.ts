/**
 * Organisation Mappers — wire ↔ domain.
 */
import type {
	ApiAbsenceRequest,
	ApiArchive,
	ApiAssignment,
	ApiAuditEvent,
	ApiInvitation,
	ApiInvite,
	ApiInvitePreview,
	ApiJoin,
	ApiJoinRequest,
	ApiManagedContract,
	ApiMember,
	ApiMemberRecord,
	ApiMembership,
	ApiOrganisation,
	ApiOrgProject,
	ApiRecord,
	ApiRecordEntry,
	ApiTeam,
	ApiTimesheet,
} from "@/shared/api";
import type {
	AbsenceRequest,
	Archive,
	Assignment,
	AuditEvent,
	Invitation,
	Invite,
	InviteInput,
	InvitePreview,
	JoinRequest,
	JoinResult,
	ManagedContract,
	Member,
	MemberRecord,
	Membership,
	Organisation,
	OrganisationCard,
	OrganisationInput,
	OrgProject,
	OrgProjectInput,
	OrgRecord,
	RecordEntry,
	Team,
	TeamInput,
	Timesheet,
} from "./types";

export function toOrganisation(api: ApiOrganisation): Organisation {
	return {
		id: api.id,
		name: api.name,
		logoUrl: api.logo_url ?? undefined,
		weekStart: api.week_start ?? "monday",
		holidayCountry: api.holiday_country ?? undefined,
		holidaySubdivision: api.holiday_subdivision ?? undefined,
		timezone: api.timezone ?? "UTC",
		createdAt: api.created_at,
	};
}

export function toApiOrganisationInput(input: OrganisationInput) {
	return {
		name: input.name,
		logo_url: input.logoUrl?.trim() || null,
		week_start: input.weekStart,
		holiday_country: input.holidayCountry || null,
		holiday_subdivision: input.holidaySubdivision || null,
		timezone: input.timezone,
	};
}

function toCard(api: { id: string; name: string; logo_url?: string | null }): OrganisationCard {
	return { id: api.id, name: api.name, logoUrl: api.logo_url ?? undefined };
}

export function toMembership(api: ApiMembership): Membership {
	return {
		userId: api.user_id,
		organisation: toOrganisation(api.organisation),
		role: api.role,
		joinedAt: api.joined_at,
		leftAt: api.left_at ?? undefined,
		leftReason: api.left_reason ?? undefined,
	};
}

export function toMember(api: ApiMember): Member {
	return {
		userId: api.user_id,
		name: api.name,
		email: api.email,
		role: api.role,
		joinedAt: api.joined_at,
		leftAt: api.left_at ?? undefined,
	};
}

export function toInvite(api: ApiInvite): Invite {
	return {
		id: api.id,
		email: api.email ?? undefined,
		role: api.role,
		requiresApproval: api.requires_approval,
		token: api.token,
		createdAt: api.created_at,
		expiresAt: api.expires_at,
		acceptedAt: api.accepted_at ?? undefined,
	};
}

export function toApiInviteInput(input: InviteInput) {
	return {
		email: input.email?.trim() || null,
		role: input.role,
		requires_approval: input.requiresApproval,
		expires_in_days: input.expiresInDays,
	};
}

export function toInvitation(api: ApiInvitation): Invitation {
	return {
		role: api.role,
		expiresAt: api.expires_at,
		organisation: toCard(api.organisation),
	};
}

export function toInvitePreview(api: ApiInvitePreview): InvitePreview {
	return {
		organisation: toCard(api.organisation),
		role: api.role,
		requiresApproval: api.requires_approval,
		addressed: api.addressed,
		alreadyMember: api.already_member,
	};
}

export function toJoinResult(api: ApiJoin): JoinResult {
	if (api.status === "joined" && api.membership) {
		return { status: "joined", membership: toMembership(api.membership) };
	}
	return { status: "pending" };
}

export function toJoinRequest(api: ApiJoinRequest): JoinRequest {
	return {
		id: api.id,
		userId: api.user_id,
		name: api.name,
		email: api.email,
		requestedAt: api.requested_at,
	};
}

export function toAssignment(api: ApiAssignment): Assignment {
	return {
		userId: api.user_id,
		name: api.name ?? undefined,
		sharedFrom: api.shared_from,
		assignedAt: api.assigned_at,
		endedAt: api.ended_at ?? undefined,
		hasContract: api.has_contract,
	};
}

function toProjectFields(api: Omit<ApiOrgProject, "members">): Omit<OrgProject, "members"> {
	return {
		id: api.id,
		name: api.name,
		description: api.description ?? undefined,
		color: api.color ?? undefined,
		archived: api.archived ?? false,
		kind: api.kind ?? "side_project",
		githubRepo: api.github_repo ?? undefined,
		category: api.category ?? undefined,
	};
}

export function toOrgProject(api: ApiOrgProject): OrgProject {
	return { ...toProjectFields(api), members: api.members.map(toAssignment) };
}

/** Every field is sent: an update replaces what the organisation had. */
export function toApiOrgProjectInput(input: OrgProjectInput) {
	return {
		name: input.name,
		description: input.description?.trim() || null,
		color: input.color || null,
		kind: input.kind,
		github_repo: input.githubRepo?.trim() || null,
		category: input.category?.trim() || null,
		archived: input.archived,
	};
}

function toEntry(api: ApiRecordEntry): RecordEntry {
	return {
		id: api.id,
		day: api.day,
		start: api.start,
		end: api.end,
		hours: api.hours,
		note: api.note ?? undefined,
	};
}

function toMemberRecord(api: ApiMemberRecord): MemberRecord {
	return {
		userId: api.user_id,
		name: api.name,
		sharedFrom: api.shared_from,
		active: api.active,
		hours: api.hours,
		entries: api.entries.map(toEntry),
		absences: api.absences.map((a) => ({ date: a.date, type: a.type, halfDay: a.half_day })),
		hasContract: api.has_contract,
		balance: api.balance
			? {
					asOf: api.balance.as_of,
					balance: api.balance.balance,
					opening: api.balance.opening,
					worked: api.balance.worked,
					expectedThrough: api.balance.expected_through,
					adjusted: api.balance.adjusted,
				}
			: undefined,
		totals: {
			entries: api.totals.entries,
			hours: api.totals.hours,
			first: api.totals.first ?? undefined,
			last: api.totals.last ?? undefined,
		},
	};
}

export function toRecord(api: ApiRecord): OrgRecord {
	return {
		organisation: toCard(api.organisation),
		month: api.month,
		first: api.first,
		last: api.last,
		projects: api.projects.map((p) => ({
			project: toProjectFields(p.project),
			members: p.members.map(toMemberRecord),
		})),
	};
}

export function toArchive(api: ApiArchive): Archive {
	return {
		organisation: toCard(api.organisation),
		role: api.role,
		joinedAt: api.joined_at,
		leftAt: api.left_at ?? undefined,
		hours: api.hours,
		projects: api.projects.map((p) => ({
			projectId: p.project_id,
			name: p.name,
			color: p.color ?? undefined,
			hours: p.hours,
			entries: p.entries.map(toEntry),
			absences: p.absences.map((a) => ({ date: a.date, type: a.type, halfDay: a.half_day })),
		})),
	};
}

// Employment (stages 3 and 4).

export function toTeam(api: ApiTeam): Team {
	return { id: api.id, name: api.name, memberIds: api.member_ids };
}

export function toApiTeamInput(input: TeamInput) {
	return { name: input.name, member_ids: input.memberIds };
}

export function toAbsenceRequest(api: ApiAbsenceRequest): AbsenceRequest {
	return {
		id: api.id,
		projectId: api.project_id,
		projectName: api.project_name ?? undefined,
		userId: api.user_id,
		memberName: api.member_name ?? undefined,
		date: api.date,
		type: api.type,
		halfDay: api.half_day,
		note: api.note ?? undefined,
		status: api.status,
		requestedAt: api.requested_at,
		decidedAt: api.decided_at ?? undefined,
		decidedBy: api.decided_by ?? undefined,
		decidedByName: api.decided_by_name ?? undefined,
		comment: api.comment ?? undefined,
	};
}

export function toTimesheet(api: ApiTimesheet): Timesheet {
	return {
		id: api.id,
		projectId: api.project_id,
		projectName: api.project_name ?? undefined,
		userId: api.user_id,
		memberName: api.member_name ?? undefined,
		month: api.month,
		status: api.status,
		submittedAt: api.submitted_at,
		decidedAt: api.decided_at ?? undefined,
		decidedBy: api.decided_by ?? undefined,
		decidedByName: api.decided_by_name ?? undefined,
		comment: api.comment ?? undefined,
		frozen: api.frozen
			? {
					worked: api.frozen.worked,
					expected: api.frozen.expected,
					balanceEnd: api.frozen.balance_end,
					entries: api.frozen.entries,
					absenceDays: api.frozen.absence_days,
				}
			: undefined,
		history: api.history.map((h) => ({
			at: h.at,
			by: h.by,
			action: h.action,
			comment: h.comment ?? undefined,
		})),
	};
}

export function toManagedContract(api: ApiManagedContract): ManagedContract {
	return {
		projectId: api.project_id,
		userId: api.user_id,
		managed: api.managed,
		contract: api.contract ?? null,
	};
}

export function toAuditEvent(api: ApiAuditEvent): AuditEvent {
	return {
		at: api.at,
		actorUserId: api.actor_user_id ?? undefined,
		event: api.event,
		subjectUserId: api.subject_user_id ?? undefined,
		projectId: api.project_id ?? undefined,
		details: api.details,
	};
}
