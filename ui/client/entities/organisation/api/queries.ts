/**
 * Organisation TanStack Query Hooks (docs/organisations.md).
 *
 * Every read hangs off `organisationsRootKey`. A write that changes what a
 * member sees of their own projects — joining, leaving, being assigned,
 * connecting a project — also invalidates the project list, since an
 * organisation's project is on it or not because of these.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { projectKeys } from "@/entities/project";
import { sessionKeys } from "@/entities/session";
import { organisationsRootKey } from "@/shared/api";
import type { InviteInput, OrganisationInput, OrgProjectInput, OrgRole } from "../model";
import {
	assignMember,
	connectProject,
	createInvite,
	createOrganisation,
	createOrgProject,
	decideJoinRequest,
	fetchArchive,
	fetchInvitations,
	fetchInvitePreview,
	fetchInvites,
	fetchJoinRequests,
	fetchMembers,
	fetchMembership,
	fetchMemberships,
	fetchOrgProjects,
	fetchRecord,
	fetchVisible,
	joinOrganisation,
	leaveOrganisation,
	removeMember,
	revokeInvite,
	setMemberRole,
	unassignMember,
	updateOrganisation,
	updateOrgProject,
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
	});
}

/** What the organisation sees of the caller in a month. */
export function useVisible(organisationId: string, month: string) {
	return useQuery({
		queryKey: organisationKeys.visible(organisationId, month),
		queryFn: () => fetchVisible(organisationId, month),
	});
}

export function useArchive(organisationId: string) {
	return useQuery({
		queryKey: organisationKeys.archive(organisationId),
		queryFn: () => fetchArchive(organisationId),
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

export function useAssignMember(organisationId: string) {
	const invalidate = useInvalidateTimeline();
	return useMutation({
		mutationFn: ({ projectId, userId }: { projectId: string; userId: string }) =>
			assignMember(organisationId, projectId, userId),
		onSuccess: invalidate,
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
