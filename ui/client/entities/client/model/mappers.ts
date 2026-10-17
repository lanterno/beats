import type { ApiClient, ApiCurrency, ApiRateTerm } from "@/shared/api";
import type { Client, ClientInput, Currency, RateTerm } from "./types";

function toRateTerm(api: ApiRateTerm): RateTerm {
	return { effectiveFrom: api.effective_from, rateMinor: api.rate_minor };
}

export function toClient(api: ApiClient): Client {
	return {
		id: api.id,
		name: api.name,
		contactName: api.contact_name ?? undefined,
		contactEmail: api.contact_email ?? undefined,
		currency: api.currency,
		minorUnits: api.minor_units,
		rates: api.rates.map(toRateTerm),
		archived: api.archived,
		createdAt: api.created_at,
		currencyLocked: api.currency_locked,
	};
}

export function toCurrency(api: ApiCurrency): Currency {
	return { code: api.code, minorUnits: api.minor_units };
}

/**
 * The write body. Every key is sent, null where it may be, since the API
 * requires them all: a key left out is a 422, never a field quietly kept or
 * wiped. A contact that is only whitespace is none.
 */
export function toApiClientInput(input: ClientInput) {
	return {
		name: input.name.trim(),
		contact_name: input.contactName?.trim() || null,
		contact_email: input.contactEmail?.trim() || null,
		currency: input.currency,
		rates: input.rates.map((rate) => ({
			effective_from: rate.effectiveFrom,
			rate_minor: rate.rateMinor,
		})),
	};
}
