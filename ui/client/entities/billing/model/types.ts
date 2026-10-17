/**
 * Billing Domain Types
 * A freelance project's billing, the marks on single entries, and what a
 * month comes to per client (docs/billing.md). Money is integer minor units
 * of the client's one currency, with its `minorUnits` beside it; every
 * amount and hour figure here is the API's.
 */

/**
 * From `effectiveFrom` on, whether the project's hours are billable and,
 * optionally, at a rate of its own; without one they take the client's
 * rate in force each day.
 */
export interface BillingTerm {
	effectiveFrom: string; // YYYY-MM-DD
	billable: boolean;
	rateMinor?: number; // per hour; never on a term that is not billable
}

/** One project's billing: its client, and its terms ascending by `effectiveFrom`. */
export interface ProjectBilling {
	projectId: string;
	clientId: string;
	/** The client's currency, which every `rateMinor` here is in. */
	currency: string;
	minorUnits: number;
	terms: BillingTerm[];
}

/** What a project billing write sends: the client and the whole list of terms. */
export interface ProjectBillingInput {
	clientId: string;
	terms: BillingTerm[];
}

/** Where a line's rate came from: the project's own term, or the client's default. */
export type RateSource = "client" | "project";

/**
 * A run of consecutive days of one project at one rate from one source.
 * `rateMinor`, `source` and `amountMinor` are absent together on a run with
 * no rate at either level. `amountMinor` is `hours` × `rateMinor`, rounded
 * once, so the printed figures multiply out.
 */
export interface BillingLine {
	projectId: string;
	projectName: string;
	rateMinor?: number;
	source?: RateSource;
	first: string; // YYYY-MM-DD
	last: string; // YYYY-MM-DD
	hours: number;
	amountMinor?: number;
}

/** A finished entry of a billed project. `hours` is for display; the lines are the figures. */
export interface BillingEntry {
	beatId: string;
	projectId: string;
	/** The local day it started on, which decides its month and its rate. */
	day: string; // YYYY-MM-DD
	start: string; // ISO datetime
	end: string; // ISO datetime
	hours: number;
	billable: boolean;
	/** A mark of the user's decides it, not the project's term. */
	overridden: boolean;
	rateMinor?: number;
}

/** One client's month, in its one currency. The hours and the amount are sums of the lines. */
export interface ClientBilling {
	clientId: string;
	name: string;
	archived: boolean;
	currency: string;
	minorUnits: number;
	/** A billable timer is running; it counts once it stops. */
	running: boolean;
	billableHours: number;
	nonBillableHours: number;
	/** The part of `billableHours` with no rate. */
	unpricedHours: number;
	amountMinor: number;
	lines: BillingLine[];
	entries: BillingEntry[];
}

/** Every listed client in one currency. No figure holds two currencies. */
export interface CurrencyTotal {
	currency: string;
	minorUnits: number;
	billableHours: number;
	unpricedHours: number;
	amountMinor: number;
}

/** A freelance project with finished hours in the month and no client: hours in no figure. */
export interface UnattachedHours {
	projectId: string;
	name: string;
	hours: number;
}

/** What is billable in a month: all of it once over, `first` through today while it runs. */
export interface BillingMonth {
	month: string; // YYYY-MM
	first: string; // YYYY-MM-DD
	last: string; // YYYY-MM-DD
	totals: CurrencyTotal[];
	clients: ClientBilling[];
	unattached: UnattachedHours[];
}
