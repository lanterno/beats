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

/** What a billing budget limits: every project billed to a client, or one billed project. */
export type BillingBudgetScope = "client" | "project";

/** Hours, or money in the scope's client's one currency. */
export type BillingBudgetUnit = "hours" | "money";

/** The calendar month, every month; or one cap from `startsOn` on, with no end. */
export type BillingBudgetPeriod = "monthly" | "total";

/** Under the warning, past it, or at or past the limit. Over is a negative remaining. */
export type BillingBudgetState = "under" | "near" | "used_up";

/**
 * What a billing budget write sends: every key, the other unit's limit and
 * a monthly budget's `startsOn` as absent, which go out as null.
 */
export interface BillingBudgetInput {
	unit: BillingBudgetUnit;
	period: BillingBudgetPeriod;
	/** To the hundredth; only on an hours budget. */
	limitHours?: number;
	/** In the client's currency; only on a money budget. */
	limitMinor?: number;
	/** YYYY-MM-DD; only on a total. */
	startsOn?: string;
	/** 1 to 99; 100 % is always the second threshold. */
	warnAtPercent: number;
}

/** A billing budget as stored, with its client's currency beside a money limit. */
export interface BillingBudget extends BillingBudgetInput {
	scope: BillingBudgetScope;
	scopeId: string;
	clientId: string;
	currency: string;
	minorUnits: number;
}

/**
 * A running timer that counts on the budget. `nearAt` and `overAt` are the
 * instants (UTC ISO) at which this timer alone would cross the warning and
 * the limit: absent once crossed, and both absent when it has no rate under
 * a money budget or another timer counts too.
 */
export interface BillingBudgetRunning {
	projectId: string;
	since: string; // ISO datetime
	priced: boolean;
	nearAt?: string;
	overAt?: string;
}

/**
 * A billing budget read as of today: the current month, or a total from
 * `startsOn` through today. The three figures are there whatever the unit;
 * only the unit's own remaining figure is, negative when over. No figure
 * counts a running timer: `running` answers it. An upcoming total has no
 * figures, no projection and no running timer. `active` is false while its
 * client or project is archived: it is read, but never alerts.
 */
export interface BillingBudgetStatus extends BillingBudget {
	/** The client's name, or the project's. */
	name: string;
	active: boolean;
	upcoming: boolean;
	first: string; // YYYY-MM-DD
	/** The month's last day; absent on a total. */
	last?: string;
	/** Today; absent while upcoming. */
	through?: string;
	billableHours: number;
	/** The part of `billableHours` with no rate. */
	unpricedHours: number;
	amountMinor: number;
	remainingHours?: number;
	remainingMinor?: number;
	/** Rounded down and not capped, so it never reads 100 before the limit. */
	percentUsed: number;
	state: BillingBudgetState;
	/** YYYY-MM-DD, at the recent pace; absent wherever the API makes no guess. */
	runsOutOn?: string;
	running?: BillingBudgetRunning;
}
