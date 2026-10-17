/**
 * Client API Functions
 * Under /api/clients, outside every device-token prefix, and the currency
 * table under /api/meta/currencies.
 */

import {
	ApiClientListSchema,
	ApiClientSchema,
	CurrencyListSchema,
	del,
	get,
	parseApiResponse,
	post,
	put,
} from "@/shared/api";
import { browserTimeZone } from "@/shared/lib";
import type { Client, ClientInput, Currency } from "../model";
import { toApiClientInput, toClient, toCurrency } from "../model";

/** The active clients, or with `archived` the archived ones, by name. */
export async function fetchClients(archived = false): Promise<Client[]> {
	const data = await get<unknown>(`/api/clients/?archived=${archived}`);
	return parseApiResponse(ApiClientListSchema, data).map(toClient);
}

/** 400 UNKNOWN_CURRENCY for a code the API's table does not know. */
export async function createClient(input: ClientInput): Promise<Client> {
	const data = await post<unknown>("/api/clients/", toApiClientInput(input));
	return toClient(parseApiResponse(ApiClientSchema, data));
}

/**
 * Replace a client. A rate change dated before the current month is a 409
 * RETROACTIVE_CHANGE unless `rewritePast` says the user has confirmed it
 * (`withPastConsent`); a currency change once something is priced in it is
 * a 409 CURRENCY_IN_USE.
 */
export async function updateClient(
	clientId: string,
	input: ClientInput,
	rewritePast: boolean,
): Promise<Client> {
	const params = new URLSearchParams({ tz: browserTimeZone() });
	const data = await put<unknown>(`/api/clients/${clientId}?${params.toString()}`, {
		...toApiClientInput(input),
		rewrite_past: rewritePast,
	});
	return toClient(parseApiResponse(ApiClientSchema, data));
}

export async function archiveClient(clientId: string): Promise<Client> {
	const data = await post<unknown>(`/api/clients/${clientId}/archive`);
	return toClient(parseApiResponse(ApiClientSchema, data));
}

export async function unarchiveClient(clientId: string): Promise<Client> {
	const data = await post<unknown>(`/api/clients/${clientId}/unarchive`);
	return toClient(parseApiResponse(ApiClientSchema, data));
}

/** 409 CLIENT_HAS_PROJECTS while a project is billed to it; archive instead. */
export async function deleteClient(clientId: string): Promise<void> {
	await del<void>(`/api/clients/${clientId}`);
}

export async function fetchCurrencies(): Promise<Currency[]> {
	const data = await get<unknown>("/api/meta/currencies");
	return parseApiResponse(CurrencyListSchema, data).map(toCurrency);
}
