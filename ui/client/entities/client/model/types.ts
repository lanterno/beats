/**
 * Client Domain Types
 * Who you bill: a record in your own account, in one currency, with a dated
 * default rate (docs/billing.md).
 */

/** One stretch of a client's default rate, from `effectiveFrom` until the next. */
export interface RateTerm {
	effectiveFrom: string; // YYYY-MM-DD, any day of the week
	rateMinor: number; // per hour, in the currency's minor units
}

export interface Client {
	id: string;
	name: string;
	contactName?: string;
	/** Shown, never mailed. */
	contactEmail?: string;
	currency: string; // ISO 4217
	/** The currency's minor units, from the API's table. */
	minorUnits: number;
	/** Ascending by `effectiveFrom`, as the API keeps them. */
	rates: RateTerm[];
	/** Kept, in the reports of months it has hours in, and out of the pickers. */
	archived: boolean;
	createdAt: string; // ISO datetime
	/** Something is priced in the currency, so it can no longer change. */
	currencyLocked: boolean;
}

/** What a client write sends: every field, an empty contact being none. */
export interface ClientInput {
	name: string;
	contactName?: string;
	contactEmail?: string;
	currency: string;
	rates: RateTerm[];
}

/** A currency a client may be billed in. */
export interface Currency {
	code: string;
	minorUnits: number;
}
