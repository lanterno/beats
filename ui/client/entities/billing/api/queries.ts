/**
 * Billing TanStack Query Hooks
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { billingRootKey, clientsRootKey } from "@/shared/api";
import type {
	BillingBudgetInput,
	BillingBudgetScope,
	BillingBudgetStatus,
	BillingMonth,
	ProjectBilling,
	ProjectBillingInput,
	Report,
	ReportLink,
	ReportLinkInput,
} from "../model";
import {
	clearEntryBillable,
	createReportLink,
	deleteBillingBudget,
	deleteReportLink,
	fetchBillableOverrides,
	fetchBillingBudgets,
	fetchBillingMonth,
	fetchProjectBillings,
	fetchReport,
	fetchReportLinks,
	putBillingBudget,
	removeProjectBilling,
	setEntryBillable,
	setProjectBilling,
} from "./billingApi";

/**
 * Every key sits under `billingRootKey`, which a session or timer write in
 * another entity invalidates (`shared/api/keys.ts`): an entry's hours, day
 * and project are what the month's figures are made of.
 */
const billingKeys = {
	all: billingRootKey,
	projects: () => [...billingKeys.all, "projects"] as const,
	entries: () => [...billingKeys.all, "entries"] as const,
	month: (month: string, tz: string) => [...billingKeys.all, "month", month, tz] as const,
	budgets: (tz: string) => [...billingKeys.all, "budgets", tz] as const,
	links: (clientId: string) => [...billingKeys.all, "links", clientId] as const,
};

/**
 * Every billed project's billing, by project id. A project not in it is not
 * billed. `enabled: false` where no project on screen could be — a page of a
 * day job reads nothing of billing.
 */
export function useProjectBillings({ enabled = true }: { enabled?: boolean } = {}) {
	return useQuery({
		queryKey: billingKeys.projects(),
		queryFn: (): Promise<Map<string, ProjectBilling>> => fetchProjectBillings(),
		enabled,
	});
}

/** Every entry mark, by entry id. */
export function useBillableOverrides({ enabled = true }: { enabled?: boolean } = {}) {
	return useQuery({
		queryKey: billingKeys.entries(),
		queryFn: (): Promise<Map<string, boolean>> => fetchBillableOverrides(),
		enabled,
	});
}

/**
 * The month's figures. Never fresh from the cache: they are the page's
 * whole point, and any entry, mark or rate written since moves them.
 */
export function useBillingMonth(month: string, tz: string) {
	return useQuery({
		queryKey: billingKeys.month(month, tz),
		queryFn: (): Promise<BillingMonth> => fetchBillingMonth(month, tz),
		staleTime: 0,
	});
}

/**
 * Every billing budget, read as of today. Never fresh from the cache, as the
 * month: any entry, mark, rate or timer written since moves it, and it sits
 * under the billing root so each of those refreshes it. No interval: a
 * running timer's crossings are instants, which the page compares with the
 * clock (`billingBudgetState`). `enabled: false` where nothing on screen
 * reads a budget — a past month, a nav with no Clients.
 */
export function useBillingBudgets(tz: string, { enabled = true }: { enabled?: boolean } = {}) {
	return useQuery({
		queryKey: billingKeys.budgets(tz),
		queryFn: (): Promise<BillingBudgetStatus[]> => fetchBillingBudgets(tz),
		staleTime: 0,
		enabled,
	});
}

/**
 * A billing write moves every billing figure, and the clients too: whether
 * a client's currency is locked depends on a project of it having a rate,
 * or on a money billing budget.
 */
function useInvalidateAfterBillingWrite() {
	const queryClient = useQueryClient();
	return () =>
		Promise.all([
			queryClient.invalidateQueries({ queryKey: billingKeys.all }),
			queryClient.invalidateQueries({ queryKey: clientsRootKey }),
		]);
}

/**
 * Bill a project, or replace its client and terms. Send it through
 * `withPastConsent`, which asks again with `rewritePast` once the user has
 * confirmed a change to a month already over.
 */
export function useSetProjectBilling() {
	const invalidate = useInvalidateAfterBillingWrite();
	return useMutation({
		mutationFn: ({
			projectId,
			input,
			rewritePast,
		}: {
			projectId: string;
			input: ProjectBillingInput;
			rewritePast: boolean;
		}) => setProjectBilling(projectId, input, rewritePast),
		onSuccess: invalidate,
		// A 409 is the answer the consent flow asks the user about.
		retry: false,
	});
}

/**
 * Stop billing a project, through `withPastConsent` like the set.
 * `removeBillingBudget` is true only from a confirmation that named the
 * project's budget; without it the API refuses while there is one.
 */
export function useRemoveProjectBilling() {
	const invalidate = useInvalidateAfterBillingWrite();
	return useMutation({
		mutationFn: ({
			projectId,
			rewritePast,
			removeBillingBudget,
		}: {
			projectId: string;
			rewritePast: boolean;
			removeBillingBudget: boolean;
		}) => removeProjectBilling(projectId, rewritePast, removeBillingBudget),
		onSuccess: invalidate,
		retry: false,
	});
}

/** Give a client or a billed project its billing budget, replacing the one it had. */
export function useSetBillingBudget() {
	const invalidate = useInvalidateAfterBillingWrite();
	return useMutation({
		mutationFn: ({
			scope,
			scopeId,
			input,
		}: {
			scope: BillingBudgetScope;
			scopeId: string;
			input: BillingBudgetInput;
		}) => putBillingBudget(scope, scopeId, input),
		onSuccess: invalidate,
		retry: false,
	});
}

/** Take a billing budget away. */
export function useRemoveBillingBudget() {
	const invalidate = useInvalidateAfterBillingWrite();
	return useMutation({
		mutationFn: ({ scope, scopeId }: { scope: BillingBudgetScope; scopeId: string }) =>
			deleteBillingBudget(scope, scopeId),
		onSuccess: invalidate,
		retry: false,
	});
}

/**
 * A mark changes in the cache at once, so the pill answers the tap; it is
 * put back if the write fails, and the month's figures are read again once
 * it has landed either way.
 */
function useWriteEntryMark<V extends { beatId: string }>(
	write: (variables: V) => Promise<void>,
	apply: (marks: Map<string, boolean>, variables: V) => void,
) {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: write,
		onMutate: async (variables: V) => {
			await queryClient.cancelQueries({ queryKey: billingKeys.entries() });
			const prev = queryClient.getQueryData<Map<string, boolean>>(billingKeys.entries());
			if (prev) {
				const next = new Map(prev);
				apply(next, variables);
				queryClient.setQueryData(billingKeys.entries(), next);
			}
			return { prev };
		},
		onError: (_error, _variables, context) => {
			if (context?.prev) queryClient.setQueryData(billingKeys.entries(), context.prev);
		},
		onSettled: () => queryClient.invalidateQueries({ queryKey: billingKeys.all }),
	});
}

/** Mark one entry billable or not, against its project's term. */
export function useSetEntryBillable() {
	return useWriteEntryMark(
		({ beatId, billable }: { beatId: string; billable: boolean }) =>
			setEntryBillable(beatId, billable),
		(marks, { beatId, billable }) => marks.set(beatId, billable),
	);
}

/** Return an entry to its project's rule. */
export function useClearEntryBillable() {
	return useWriteEntryMark(
		({ beatId }: { beatId: string }) => clearEntryBillable(beatId),
		(marks, { beatId }) => marks.delete(beatId),
	);
}

/**
 * One client's report links. Under the billing root like everything else
 * here, though no session or timer write moves a link: it keeps one entity
 * owning one root, and the list is small.
 */
export function useReportLinks(clientId: string, { enabled = true }: { enabled?: boolean } = {}) {
	return useQuery({
		queryKey: billingKeys.links(clientId),
		queryFn: (): Promise<ReportLink[]> => fetchReportLinks(clientId),
		enabled,
	});
}

/**
 * How many report links work right now across the given clients. Every link
 * listed works: revoking deletes one, and an archived client's links still
 * serve (docs/billing.md, 1c). Read fresh each time, never from the cache,
 * since a link minted a moment ago on another device counts. It reads through
 * the keys `useReportLinks` fills, so the Clients page gets the lists too.
 */
export function useCountReportLinks(): (clientIds: readonly string[]) => Promise<number> {
	const queryClient = useQueryClient();
	return useCallback(
		async (clientIds) => {
			const lists = await Promise.all(
				clientIds.map((clientId) =>
					queryClient.fetchQuery({
						queryKey: billingKeys.links(clientId),
						queryFn: (): Promise<ReportLink[]> => fetchReportLinks(clientId),
						staleTime: 0,
					}),
				),
			);
			return lists.reduce((total, links) => total + links.length, 0);
		},
		[queryClient],
	);
}

/** Mint a link over a fixed range. */
export function useCreateReportLink() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: ({ clientId, input }: { clientId: string; input: ReportLinkInput }) =>
			createReportLink(clientId, input),
		onSuccess: (_link, { clientId }) =>
			queryClient.invalidateQueries({ queryKey: billingKeys.links(clientId) }),
		retry: false,
	});
}

/** Revoke a link. */
export function useDeleteReportLink() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: ({ clientId, linkId }: { clientId: string; linkId: string }) =>
			deleteReportLink(clientId, linkId),
		onSuccess: (_void, { clientId }) =>
			queryClient.invalidateQueries({ queryKey: billingKeys.links(clientId) }),
		retry: false,
	});
}

/**
 * The public read, for the page a client opens. Outside `billingRootKey`:
 * the reader has no account, so there is no cache of theirs to invalidate,
 * and nothing in the app writes what it shows. Not retried on a 404 — a
 * revoked link will not come back.
 */
export function useReport(token: string) {
	return useQuery({
		queryKey: ["report", token] as const,
		queryFn: (): Promise<Report> => fetchReport(token),
		retry: false,
	});
}
