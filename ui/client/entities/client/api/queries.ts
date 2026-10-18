/**
 * Client TanStack Query Hooks
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { billingRootKey, clientsRootKey, reportLinksRootKey } from "@/shared/api";
import type { Client, ClientInput, Currency } from "../model";
import {
	archiveClient,
	createClient,
	deleteClient,
	fetchClients,
	fetchCurrencies,
	unarchiveClient,
	updateClient,
} from "./clientApi";

export const clientKeys = {
	all: clientsRootKey,
	list: (archived: boolean) =>
		[...clientKeys.all, "list", archived ? "archived" : "active"] as const,
};

/** The currency table changes only with a release of the API. */
const currencyKeys = {
	all: ["meta", "currencies"] as const,
};

/** The active clients, or with `archived` the archived ones, by name. */
export function useClients({ archived = false }: { archived?: boolean } = {}) {
	return useQuery({
		queryKey: clientKeys.list(archived),
		queryFn: (): Promise<Client[]> => fetchClients(archived),
	});
}

export function useCurrencies() {
	return useQuery({
		queryKey: currencyKeys.all,
		queryFn: (): Promise<Currency[]> => fetchCurrencies(),
		// Static for the life of the API process; the route says max-age=86400 too.
		staleTime: 24 * 60 * 60_000,
		gcTime: 24 * 60 * 60_000,
	});
}

/**
 * A client write moves the clients and every billing figure: a rate is
 * what the month's amounts are priced at, and the name and the archived
 * flag are what the report lists. Project billing is under the same root,
 * and its `currency` is the client's.
 */
function useInvalidateAfterClientWrite() {
	const queryClient = useQueryClient();
	return () =>
		Promise.all([
			queryClient.invalidateQueries({ queryKey: clientKeys.all }),
			queryClient.invalidateQueries({ queryKey: billingRootKey }),
		]);
}

export function useCreateClient() {
	const invalidate = useInvalidateAfterClientWrite();
	return useMutation({
		mutationFn: (input: ClientInput) => createClient(input),
		onSuccess: invalidate,
	});
}

/**
 * Replace a client. Send it through `withPastConsent` (entities/billing),
 * which asks again with `rewritePast` once the user has confirmed a change
 * to a month already over.
 */
export function useUpdateClient() {
	const invalidate = useInvalidateAfterClientWrite();
	return useMutation({
		mutationFn: ({
			clientId,
			input,
			rewritePast,
		}: {
			clientId: string;
			input: ClientInput;
			rewritePast: boolean;
		}) => updateClient(clientId, input, rewritePast),
		onSuccess: invalidate,
		// A 409 is the answer the consent flow asks the user about; sending
		// the same body again would only get it twice.
		retry: false,
	});
}

export function useArchiveClient() {
	const invalidate = useInvalidateAfterClientWrite();
	return useMutation({
		mutationFn: (clientId: string) => archiveClient(clientId),
		onSuccess: invalidate,
	});
}

export function useUnarchiveClient() {
	const invalidate = useInvalidateAfterClientWrite();
	return useMutation({
		mutationFn: (clientId: string) => unarchiveClient(clientId),
		onSuccess: invalidate,
	});
}

/** A deleted client's report links go with it, so they are read again too. */
export function useDeleteClient() {
	const queryClient = useQueryClient();
	const invalidate = useInvalidateAfterClientWrite();
	return useMutation({
		mutationFn: (clientId: string) => deleteClient(clientId),
		onSuccess: () =>
			Promise.all([invalidate(), queryClient.invalidateQueries({ queryKey: reportLinksRootKey })]),
		// 409 CLIENT_HAS_PROJECTS is an answer, not a failure to retry.
		retry: false,
	});
}
