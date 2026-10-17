/**
 * Billing TanStack Query Hooks
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { billingRootKey, clientsRootKey } from "@/shared/api";
import type { BillingMonth, ProjectBilling, ProjectBillingInput } from "../model";
import {
	clearEntryBillable,
	fetchBillableOverrides,
	fetchBillingMonth,
	fetchProjectBillings,
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
};

/** Every billed project's billing, by project id. A project not in it is not billed. */
export function useProjectBillings() {
	return useQuery({
		queryKey: billingKeys.projects(),
		queryFn: (): Promise<Map<string, ProjectBilling>> => fetchProjectBillings(),
	});
}

/** Every entry mark, by entry id. */
export function useBillableOverrides() {
	return useQuery({
		queryKey: billingKeys.entries(),
		queryFn: (): Promise<Map<string, boolean>> => fetchBillableOverrides(),
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
 * A billing write moves every billing figure, and the clients too: whether
 * a client's currency is locked depends on a project of it having a rate.
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

/** Stop billing a project, through `withPastConsent` like the set. */
export function useRemoveProjectBilling() {
	const invalidate = useInvalidateAfterBillingWrite();
	return useMutation({
		mutationFn: ({ projectId, rewritePast }: { projectId: string; rewritePast: boolean }) =>
			removeProjectBilling(projectId, rewritePast),
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
