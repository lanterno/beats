/**
 * Organisation TanStack Query Hooks (docs/organisations.md).
 *
 * Every read hangs off `organisationsRootKey`. A write that changes what a
 * member sees of their own projects — joining, leaving, being assigned,
 * connecting a project — also invalidates the project list, since an
 * organisation's project is on it or not because of these.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { projectKeys } from "@/entities/project";
import { sessionKeys } from "@/entities/session";
import { organisationsRootKey } from "@/shared/api";
import type { InviteInput, OrganisationInput, OrgProjectInput, OrgRole, TeamInput } from "../model";
import {
	assignMember,
	connectProject,
	createInvite,
	createOrganisation,
	createOrgProject,
	createTeam,
	decideAbsenceRequest,
	decideJoinRequest,
	decideTimesheet,
	deleteTeam,
	enterTime,
	fetchAbsenceRequests,
	fetchArchive,
	fetchAuditLog,
	fetchInvitations,
	fetchInvitePreview,
	fetchInvites,
	fetchJoinRequests,
	fetchManagedContract,
	fetchMembers,
	fetchMembership,
	fetchMemberships,
	fetchOrgProjects,
	fetchRecord,
	fetchTeams,
	fetchTimesheets,
	fetchVisible,
	joinOrganisation,
	leaveOrganisation,
	removeMember,
	reopenTimesheet,
	requestAbsence,
	revokeInvite,
	setManagedContract,
	setMemberRole,
	submitTimesheet,
	unassignMember,
	updateOrganisation,
	updateOrgProject,
	updateTeam,
	withdrawAbsenceRequest,
} from "./organisationApi";

export const organisationKeys = {
	all: organisationsRootKey,
	memberships: () => [...organisationKeys.all, "memberships"] as const,
	invitations: () => [...organisationKeys.all, "invitations"] as const,
	preview: (token: string) => [...organisationKeys.all, "join", token] as const,
	one: (id: string) => [...organisationKeys.all, "one", id] as const,
	members: (id: string) => [...organisationKeys.one(id), "members"] as const,
	invites: (id: string) => [...organisationKeys.one(id), "invites"] as const,
	requests: (id: string) => [...organisationKeys.one(id), "requests"] as const,
	projects: (id: string) => [...organisationKeys.one(id), "projects"] as const,
	record: (id: string, month: string) => [...organisationKeys.one(id), "record", month] as const,
	teams: (id: string) => [...organisationKeys.one(id), "teams"] as const,
	absenceRequests: (id: string, pending: boolean) =>
		[...organisationKeys.one(id), "absence-requests", pending ? "pending" : "all"] as const,
	timesheets: (id: string, month: string | undefined) =>
		[...organisationKeys.one(id), "timesheets", month ?? "all"] as const,
	managedContract: (id: string, projectId: string, userId: string) =>
		[...organisationKeys.one(id), "managed-contract", projectId, userId] as const,
	audit: (id: string) => [...organisationKeys.one(id), "audit"] as const,
	visible: (id: string, month: string) => [...organisationKeys.one(id), "visible", month] as const,
	archive: (id: string) => [...organisationKeys.one(id), "archive"] as const,
};

/** Every organisation the caller is or was in. */
export function useMemberships() {
	return useQuery({
		queryKey: organisationKeys.memberships(),
		queryFn: fetchMemberships,
		staleTime: 30_000,
	});
}

export function useMembership(organisationId: string | undefined) {
	return useQuery({
		queryKey: organisationKeys.one(organisationId ?? ""),
		queryFn: () => fetchMembership(organisationId ?? ""),
		enabled: Boolean(organisationId),
		// A membership that ended answers 404; asking again would not change it.
		retry: false,
	});
}

export function useInvitations() {
	return useQuery({
		queryKey: organisationKeys.invitations(),
		queryFn: fetchInvitations,
		staleTime: 60_000,
	});
}

export function useInvitePreview(token: string | undefined) {
	return useQuery({
		queryKey: organisationKeys.preview(token ?? ""),
		queryFn: () => fetchInvitePreview(token ?? ""),
		enabled: Boolean(token),
		retry: false,
	});
}

export function useMembers(organisationId: string, options: { enabled?: boolean } = {}) {
	return useQuery({
		queryKey: organisationKeys.members(organisationId),
		queryFn: () => fetchMembers(organisationId),
		enabled: options.enabled ?? true,
	});
}

export function useInvites(organisationId: string, options: { enabled?: boolean } = {}) {
	return useQuery({
		queryKey: organisationKeys.invites(organisationId),
		queryFn: () => fetchInvites(organisationId),
		enabled: options.enabled ?? true,
	});
}

export function useJoinRequests(organisationId: string, options: { enabled?: boolean } = {}) {
	return useQuery({
		queryKey: organisationKeys.requests(organisationId),
		queryFn: () => fetchJoinRequests(organisationId),
		enabled: options.enabled ?? true,
	});
}

export function useOrgProjects(organisationId: string, options: { enabled?: boolean } = {}) {
	return useQuery({
		queryKey: organisationKeys.projects(organisationId),
		queryFn: () => fetchOrgProjects(organisationId),
		enabled: options.enabled ?? true,
	});
}

/** What the organisation sees in a month. Admins. */
export function useOrgRecord(
	organisationId: string,
	month: string,
	options: { enabled?: boolean } = {},
) {
	return useQuery({
		queryKey: organisationKeys.record(organisationId, month),
		queryFn: () => fetchRecord(organisationId, month),
		enabled: options.enabled ?? true,
		// The month stepper keeps the month it has while the next arrives,
		// rather than emptying the page between two reads.
		placeholderData: keepPreviousData,
		// A refusal (403 to a member, 404 to a non-member) is an answer, not a
		// hiccup: asking twice more only delays showing it.
		retry: false,
	});
}

/** What the organisation sees of the caller in a month. */
export function useVisible(organisationId: string, month: string) {
	return useQuery({
		queryKey: organisationKeys.visible(organisationId, month),
		queryFn: () => fetchVisible(organisationId, month),
		placeholderData: keepPreviousData,
		retry: false,
	});
}

export function useArchive(organisationId: string) {
	return useQuery({
		queryKey: organisationKeys.archive(organisationId),
		queryFn: () => fetchArchive(organisationId),
		retry: false,
	});
}

/** The organisation's own reads, after a write to it. */
function useInvalidateOrganisation() {
	const queryClient = useQueryClient();
	return () => queryClient.invalidateQueries({ queryKey: organisationKeys.all });
}

/**
 * After a write that changes what is on the caller's own timeline: the
 * organisation's reads, the project list (an organisation's project appears
 * or leaves it) and the sessions (an entry's stamp moves with its project).
 */
function useInvalidateTimeline() {
	const queryClient = useQueryClient();
	return () =>
		Promise.all([
			queryClient.invalidateQueries({ queryKey: organisationKeys.all }),
			queryClient.invalidateQueries({ queryKey: projectKeys.all }),
			queryClient.invalidateQueries({ queryKey: sessionKeys.all }),
		]);
}

export function useCreateOrganisation() {
	const invalidate = useInvalidateOrganisation();
	return useMutation({
		mutationFn: (input: OrganisationInput) => createOrganisation(input),
		onSuccess: invalidate,
	});
}

export function useUpdateOrganisation(organisationId: string) {
	const invalidate = useInvalidateTimeline();
	return useMutation({
		mutationFn: (input: OrganisationInput) => updateOrganisation(organisationId, input),
		// The name and logo mark every member's project list.
		onSuccess: invalidate,
	});
}

export function useSetMemberRole(organisationId: string) {
	const invalidate = useInvalidateOrganisation();
	return useMutation({
		mutationFn: ({ userId, role }: { userId: string; role: OrgRole }) =>
			setMemberRole(organisationId, userId, role),
		onSuccess: invalidate,
		retry: false,
	});
}

export function useRemoveMember(organisationId: string) {
	const invalidate = useInvalidateOrganisation();
	return useMutation({
		mutationFn: (userId: string) => removeMember(organisationId, userId),
		onSuccess: invalidate,
		retry: false,
	});
}

export function useLeaveOrganisation(organisationId: string) {
	const invalidate = useInvalidateTimeline();
	return useMutation({
		mutationFn: () => leaveOrganisation(organisationId),
		onSuccess: invalidate,
		retry: false,
	});
}

export function useCreateInvite(organisationId: string) {
	const invalidate = useInvalidateOrganisation();
	return useMutation({
		mutationFn: (input: InviteInput) => createInvite(organisationId, input),
		onSuccess: invalidate,
	});
}

export function useRevokeInvite(organisationId: string) {
	const invalidate = useInvalidateOrganisation();
	return useMutation({
		mutationFn: (inviteId: string) => revokeInvite(organisationId, inviteId),
		onSuccess: invalidate,
	});
}

export function useJoinOrganisation() {
	const invalidate = useInvalidateTimeline();
	return useMutation({
		mutationFn: (token: string) => joinOrganisation(token),
		onSuccess: invalidate,
		retry: false,
	});
}

export function useDecideJoinRequest(organisationId: string) {
	const invalidate = useInvalidateOrganisation();
	return useMutation({
		mutationFn: ({
			requestId,
			decision,
		}: {
			requestId: string;
			decision: "approved" | "declined";
		}) => decideJoinRequest(organisationId, requestId, decision),
		onSuccess: invalidate,
	});
}

export function useCreateOrgProject(organisationId: string) {
	const invalidate = useInvalidateTimeline();
	return useMutation({
		mutationFn: (input: OrgProjectInput) => createOrgProject(organisationId, input),
		onSuccess: invalidate,
	});
}

export function useUpdateOrgProject(organisationId: string) {
	const invalidate = useInvalidateTimeline();
	return useMutation({
		mutationFn: ({ projectId, input }: { projectId: string; input: OrgProjectInput }) =>
			updateOrgProject(organisationId, projectId, input),
		onSuccess: invalidate,
	});
}

export function useAssignMembers(organisationId: string) {
	const invalidate = useInvalidateTimeline();
	return useMutation({
		mutationFn: async ({ projectId, userIds }: { projectId: string; userIds: string[] }) => {
			// One PUT per member, in order. Assigning is idempotent on the
			// server — an already-active assignment is returned, not doubled —
			// so sending the whole pick again after a failure partway is safe.
			for (const userId of userIds) {
				await assignMember(organisationId, projectId, userId);
			}
		},
		// A failure partway has still assigned everyone before it.
		onSettled: invalidate,
	});
}

export function useUnassignMember(organisationId: string) {
	const invalidate = useInvalidateTimeline();
	return useMutation({
		mutationFn: ({ projectId, userId }: { projectId: string; userId: string }) =>
			unassignMember(organisationId, projectId, userId),
		onSuccess: invalidate,
	});
}

/** Connect one of the caller's own projects; see `connectProject`. */
export function useConnectProject() {
	const invalidate = useInvalidateTimeline();
	return useMutation({
		mutationFn: ({
			organisationId,
			projectId,
			shareFrom,
		}: {
			organisationId: string;
			projectId: string;
			shareFrom: string | null;
		}) => connectProject(organisationId, projectId, shareFrom),
		onSuccess: invalidate,
		// A 409 is an answer the dialog shows, not something to send twice.
		retry: false,
	});
}

// --- Employment (docs/organisations.md, stages 3 and 4) -----------------------

export function useTeams(organisationId: string, options: { enabled?: boolean } = {}) {
	return useQuery({
		queryKey: organisationKeys.teams(organisationId),
		queryFn: () => fetchTeams(organisationId),
		enabled: options.enabled ?? true,
		retry: false,
	});
}

export function useSaveTeam(organisationId: string) {
	const invalidate = useInvalidateOrganisation();
	return useMutation({
		mutationFn: ({ teamId, input }: { teamId?: string; input: TeamInput }) =>
			teamId ? updateTeam(organisationId, teamId, input) : createTeam(organisationId, input),
		onSuccess: invalidate,
	});
}

export function useDeleteTeam(organisationId: string) {
	const invalidate = useInvalidateOrganisation();
	return useMutation({
		mutationFn: (teamId: string) => deleteTeam(organisationId, teamId),
		onSuccess: invalidate,
	});
}

export function useManagedContract(
	organisationId: string,
	projectId: string,
	userId: string,
	options: { enabled?: boolean } = {},
) {
	return useQuery({
		queryKey: organisationKeys.managedContract(organisationId, projectId, userId),
		queryFn: () => fetchManagedContract(organisationId, projectId, userId),
		enabled: options.enabled ?? true,
		retry: false,
	});
}

export function useSetManagedContract(organisationId: string) {
	// The member's week and contract panels read the assignment's contract,
	// so the project root refreshes too.
	const invalidate = useInvalidateTimeline();
	return useMutation({
		mutationFn: ({
			projectId,
			userId,
			contract,
			managed,
		}: {
			projectId: string;
			userId: string;
			contract: unknown | null;
			managed: boolean;
		}) => setManagedContract(organisationId, projectId, userId, contract, managed),
		onSuccess: invalidate,
		retry: false,
	});
}

export function useEnterTime(organisationId: string) {
	const invalidate = useInvalidateTimeline();
	return useMutation({
		mutationFn: ({
			projectId,
			userId,
			input,
		}: {
			projectId: string;
			userId: string;
			input: { start: string; end: string; note?: string };
		}) => enterTime(organisationId, projectId, userId, input),
		onSuccess: invalidate,
		retry: false,
	});
}

export function useAbsenceRequests(
	organisationId: string,
	options: { pending?: boolean; enabled?: boolean } = {},
) {
	const pending = options.pending ?? false;
	return useQuery({
		queryKey: organisationKeys.absenceRequests(organisationId, pending),
		queryFn: () => fetchAbsenceRequests(organisationId, pending),
		enabled: options.enabled ?? true,
	});
}

export function useRequestAbsence(organisationId: string) {
	const invalidate = useInvalidateOrganisation();
	return useMutation({
		mutationFn: (input: {
			projectId: string;
			date: string;
			type: "vacation" | "sick" | "other";
			halfDay: boolean;
			note?: string;
		}) => requestAbsence(organisationId, input),
		onSuccess: invalidate,
		retry: false,
	});
}

export function useDecideAbsenceRequest(organisationId: string) {
	// Approval books the absence on the member's project: their panels read it.
	const invalidate = useInvalidateTimeline();
	return useMutation({
		mutationFn: ({
			requestId,
			approve,
			comment,
		}: {
			requestId: string;
			approve: boolean;
			comment?: string;
		}) => decideAbsenceRequest(organisationId, requestId, approve, comment),
		onSuccess: invalidate,
		retry: false,
	});
}

export function useWithdrawAbsenceRequest(organisationId: string) {
	const invalidate = useInvalidateOrganisation();
	return useMutation({
		mutationFn: (requestId: string) => withdrawAbsenceRequest(organisationId, requestId),
		onSuccess: invalidate,
		retry: false,
	});
}

export function useTimesheets(
	organisationId: string,
	options: { month?: string; enabled?: boolean } = {},
) {
	return useQuery({
		queryKey: organisationKeys.timesheets(organisationId, options.month),
		queryFn: () => fetchTimesheets(organisationId, options.month),
		enabled: options.enabled ?? true,
	});
}

export function useSubmitTimesheet(organisationId: string) {
	const invalidate = useInvalidateOrganisation();
	return useMutation({
		mutationFn: ({ projectId, month }: { projectId: string; month: string }) =>
			submitTimesheet(organisationId, projectId, month),
		onSuccess: invalidate,
		retry: false,
	});
}

export function useDecideTimesheet(organisationId: string) {
	const invalidate = useInvalidateOrganisation();
	return useMutation({
		mutationFn: ({
			sheetId,
			approve,
			comment,
		}: {
			sheetId: string;
			approve: boolean;
			comment?: string;
		}) => decideTimesheet(organisationId, sheetId, approve, comment),
		onSuccess: invalidate,
		retry: false,
	});
}

export function useReopenTimesheet(organisationId: string) {
	const invalidate = useInvalidateOrganisation();
	return useMutation({
		mutationFn: ({ sheetId, reason }: { sheetId: string; reason: string }) =>
			reopenTimesheet(organisationId, sheetId, reason),
		onSuccess: invalidate,
		retry: false,
	});
}

export function useAuditLog(organisationId: string, options: { enabled?: boolean } = {}) {
	return useQuery({
		queryKey: organisationKeys.audit(organisationId),
		queryFn: () => fetchAuditLog(organisationId),
		enabled: options.enabled ?? true,
		retry: false,
	});
}
