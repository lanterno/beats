/**
 * Zod schemas for runtime API response validation
 * These schemas validate data from the backend API and provide type safety at runtime.
 */
import { z } from "zod";

// API Response Schemas (raw backend responses)

export const GoalOverrideSchema = z.object({
	week_of: z.string().nullable().optional(),
	effective_from: z.string().nullable().optional(),
	weekly_goal: z.number().nullable(),
	goal_type: z.enum(["target", "cap"]).nullable().optional(),
	note: z.string().nullable().optional(),
});

export type ApiGoalOverride = z.infer<typeof GoalOverrideSchema>;

// Work contracts (docs/work-contracts.md). These mirror the API's
// `ProjectKind`, `ScheduleType`, `ContractTerm`, `Contract`, `AbsenceType`,
// `Holiday`, `RegionHoliday` and `Region` schemas field for field; the validators behind
// them (which numbers a schedule type needs, terms in order) are the API's,
// and a 422 names the offending path in `fields`.

export const ProjectKindSchema = z.enum(["day_job", "freelance", "side_project"]);
export type ApiProjectKind = z.infer<typeof ProjectKindSchema>;

const ScheduleTypeSchema = z.enum(["full_time", "part_time", "custom", "objective"]);

export const ContractTermSchema = z.object({
	effective_from: z.string(), // YYYY-MM-DD
	schedule_type: ScheduleTypeSchema,
	full_time_hours: z.number().nullable().optional(),
	percentage: z.number().nullable().optional(), // fraction in (0, 1]
	weekly_hours: z.number().nullable().optional(),
	note: z.string().nullable().optional(),
});

export type ApiContractTerm = z.infer<typeof ContractTermSchema>;

const CompanyHolidaySchema = z.object({
	date: z.string(), // YYYY-MM-DD
	name: z.string(),
});

const CarryOverSchema = z.enum(["all", "capped", "none"]);

// Days for a five-day week, every figure a whole or half day; the cap only
// with `capped`. The API's field constraints are the authority.
const VacationEntitlementSchema = z.object({
	days_per_year: z.number(),
	carry_over: CarryOverSchema,
	carry_over_max_days: z.number().nullable().optional(),
	opening_on: z.string(), // YYYY-MM-DD
	opening_days: z.number(),
});

export type ApiVacationEntitlement = z.infer<typeof VacationEntitlementSchema>;

// The SPA always sends both holiday lists and `vacation` (an object or null)
// (`toApiContract`), since one left out of a write is kept and one sent empty
// is cleared.
export const ContractSchema = z.object({
	terms: z.array(ContractTermSchema),
	holiday_country: z.string().nullable().optional(),
	holiday_subdivision: z.string().nullable().optional(),
	opening_balance_hours: z.number().optional().default(0),
	ended_on: z.string().nullable().optional(),
	company_holidays: z.array(CompanyHolidaySchema),
	holidays_not_given: z.array(z.string()),
	vacation: VacationEntitlementSchema.nullable(),
});

export type ApiContract = z.infer<typeof ContractSchema>;

const AbsenceTypeSchema = z.enum(["vacation", "sick", "other"]);

export const ApiAbsenceSchema = z.object({
	id: z.string(),
	project_id: z.string(),
	date: z.string(), // YYYY-MM-DD
	half_day: z.boolean().optional().default(false),
	type: AbsenceTypeSchema,
	note: z.string().nullable().optional(),
});

export type ApiAbsence = z.infer<typeof ApiAbsenceSchema>;
export const ApiAbsenceListSchema = z.array(ApiAbsenceSchema);

// A balance adjustment (POST /adjustments): a signed `delta`, a `reset` to
// `hours`, or a `cap` at `hours`. What it moved the balance by is the
// ledger's `applied`, never this record's.
const AdjustmentKindSchema = z.enum(["delta", "reset", "cap"]);

export const ApiAdjustmentSchema = z.object({
	id: z.string(),
	project_id: z.string(),
	date: z.string(), // YYYY-MM-DD
	kind: AdjustmentKindSchema,
	hours: z.number(),
	note: z.string().nullable().optional(),
});

export type ApiAdjustment = z.infer<typeof ApiAdjustmentSchema>;

// One week of a day job against its contract (GET /contract/week). `expected`,
// `remaining` and `balance` are null — not 0 — when no time-based term is in
// force (an objective term, a week before the contract); 0 is a week the
// contract owed nothing by circumstance. `balance` is as of today whatever
// week is asked for.

const DayAbsenceSchema = z.object({
	type: AbsenceTypeSchema,
	half_day: z.boolean(),
	note: z.string().nullable().optional(),
});

export const ContractDaySchema = z.object({
	date: z.string(), // YYYY-MM-DD
	expected: z.number(),
	worked: z.number(),
	holiday: z.string().nullable().optional(),
	absence: DayAbsenceSchema.nullable().optional(),
});

export type ApiContractDay = z.infer<typeof ContractDaySchema>;

export const ContractWeekSchema = z.object({
	week_of: z.string(), // the Monday, YYYY-MM-DD
	expected: z.number().nullable(),
	worked: z.number(),
	remaining: z.number().nullable(),
	balance: z.number().nullable(),
	// The proof of `balance`: opening + worked − expected_through + adjusted,
	// as of `balance_as_of`. Null exactly when `balance` is.
	balance_as_of: z.string().nullable(), // YYYY-MM-DD
	balance_opening: z.number().nullable(),
	balance_worked: z.number().nullable(),
	balance_expected_through: z.number().nullable(),
	balance_adjusted: z.number().nullable(),
	days: z.array(ContractDaySchema),
});

export type ApiContractWeek = z.infer<typeof ContractWeekSchema>;

// The ledger (GET /ledger, docs/project-page.md): the last N weeks of
// any project, newest first, the current week included. These mirror the
// API's `Ledger`, `LedgerWeek`, `LedgerNote` and `LedgerTotals` models; what
// each figure means and when it is null is documented on the domain type.

const LedgerNoteKindSchema = z.enum(["vacation", "sick", "other", "holiday"]);

export const LedgerNoteSchema = z.object({
	date: z.string(), // YYYY-MM-DD, a weekday
	kind: LedgerNoteKindSchema,
	half_day: z.boolean().nullable().optional(), // on an absence
	name: z.string().nullable().optional(), // on a holiday
});

export type ApiLedgerNote = z.infer<typeof LedgerNoteSchema>;

export const LedgerAdjustmentSchema = z.object({
	id: z.string(),
	date: z.string(), // YYYY-MM-DD, any day of the week
	kind: AdjustmentKindSchema,
	hours: z.number(),
	note: z.string().nullable().optional(),
	applied: z.number(), // the hours it moved the balance by
});

export type ApiLedgerAdjustment = z.infer<typeof LedgerAdjustmentSchema>;

export const LedgerWeekSchema = z.object({
	week_of: z.string(), // the Monday, YYYY-MM-DD
	worked: z.number(),
	days: z.array(z.number()).length(7), // Mon..Sun
	effective_goal: z.number().nullable(),
	effective_goal_type: z.enum(["target", "cap"]),
	effective_goal_overridden: z.boolean(),
	contract_expected: z.number().nullable(),
	balance_end: z.number().nullable(),
	// What the week's work moved the balance by, null exactly when
	// `balance_end` is.
	balance_moved: z.number().nullable(),
	notes: z.array(LedgerNoteSchema),
	adjustments: z.array(LedgerAdjustmentSchema),
});

export type ApiLedgerWeek = z.infer<typeof LedgerWeekSchema>;

const LedgerTotalsSchema = z.object({
	expected: z.number(),
	worked: z.number(),
	adjusted: z.number(),
	balance: z.number(),
});

export type ApiLedgerTotals = z.infer<typeof LedgerTotalsSchema>;

export const LedgerSchema = z.object({
	since: z.string().nullable(), // contract.starts_on, YYYY-MM-DD
	totals: LedgerTotalsSchema.nullable(),
	// The close on `ended_on`, before a settlement after it.
	ended_balance: z.number().nullable(),
	weeks: z.array(LedgerWeekSchema),
});

export type ApiLedger = z.infer<typeof LedgerSchema>;

// GET /{id}/vacation: one calendar year of the entitlement, in whole or half
// days. `accrued` is null in the opening year, whose figure is the opening's.
export const VacationYearSchema = z.object({
	year: z.number(),
	accrued: z.number().nullable(),
	carried_in: z.number(),
	available: z.number(),
	booked: z.number(),
	remaining: z.number(),
});

export type ApiVacationYear = z.infer<typeof VacationYearSchema>;

// `given` is false only on a region holiday the contract does not give,
// listed with `include=not_given`.
const HolidaySchema = z.object({
	date: z.string(), // YYYY-MM-DD
	name: z.string(),
	source: z.enum(["region", "company"]),
	given: z.boolean(),
});

export const HolidayListSchema = z.array(HolidaySchema);

/** A region's public holiday, as the region gives it (`/api/meta/holidays`). */
const RegionHolidaySchema = z.object({
	date: z.string(), // YYYY-MM-DD
	name: z.string(),
});

export const RegionHolidayListSchema = z.array(RegionHolidaySchema);

const SubdivisionSchema = z.object({
	code: z.string(),
	name: z.string(),
});

const RegionSchema = z.object({
	code: z.string(), // ISO 3166-1 alpha-2
	name: z.string(),
	subdivisions: z.array(SubdivisionSchema),
});

export const RegionListSchema = z.array(RegionSchema);

// Clients and billing (docs/billing.md). These mirror the API's
// `ClientResponse`, `ProjectBillingResponse`, `BillableOverrideResponse`,
// `BillingMonthResponse` and `CurrencyResponse`. Money is integer minor
// units, and every amount travels with its `currency` and `minor_units`, the
// API's table being the one source for those. No field defaults for an older
// API: one without these routes answers 404, and the page shows its failure
// state.

const RateTermSchema = z.object({
	effective_from: z.string(), // YYYY-MM-DD
	rate_minor: z.number().int(), // per hour
});

export type ApiRateTerm = z.infer<typeof RateTermSchema>;

export const ApiClientSchema = z.object({
	id: z.string(),
	name: z.string(),
	contact_name: z.string().nullable(),
	contact_email: z.string().nullable(),
	currency: z.string(), // ISO 4217
	minor_units: z.number().int(),
	rates: z.array(RateTermSchema),
	archived: z.boolean(),
	created_at: z.string(), // ISO datetime
	// Something is priced in the currency, so it can no longer change.
	currency_locked: z.boolean(),
});

export type ApiClient = z.infer<typeof ApiClientSchema>;
export const ApiClientListSchema = z.array(ApiClientSchema);

const CurrencySchema = z.object({
	code: z.string(),
	minor_units: z.number().int(),
});

export type ApiCurrency = z.infer<typeof CurrencySchema>;
export const CurrencyListSchema = z.array(CurrencySchema);

// A term with no `rate_minor` takes the client's rate in force each day.
const BillingTermSchema = z.object({
	effective_from: z.string(), // YYYY-MM-DD
	billable: z.boolean(),
	rate_minor: z.number().int().nullable().optional(),
});

export type ApiBillingTerm = z.infer<typeof BillingTermSchema>;

export const ApiProjectBillingSchema = z.object({
	project_id: z.string(),
	client_id: z.string(),
	currency: z.string(), // the client's: every rate_minor here is in it
	minor_units: z.number().int(),
	terms: z.array(BillingTermSchema),
});

export type ApiProjectBilling = z.infer<typeof ApiProjectBillingSchema>;
export const ApiProjectBillingListSchema = z.array(ApiProjectBillingSchema);

export const ApiBillableOverrideSchema = z.object({
	beat_id: z.string(),
	billable: z.boolean(),
});

export type ApiBillableOverride = z.infer<typeof ApiBillableOverrideSchema>;
export const ApiBillableOverrideListSchema = z.array(ApiBillableOverrideSchema);

const RateSourceSchema = z.enum(["client", "project"]);

// A run of consecutive days of one project at one rate from one source;
// `rate_minor`, `source` and `amount_minor` are null together on an unpriced
// run. `amount_minor` is `hours` × `rate_minor`, rounded once.
const BillingLineSchema = z.object({
	project_id: z.string(),
	project_name: z.string(),
	rate_minor: z.number().int().nullable(),
	source: RateSourceSchema.nullable(),
	first: z.string(), // YYYY-MM-DD
	last: z.string(), // YYYY-MM-DD
	hours: z.number(),
	amount_minor: z.number().int().nullable(),
});

export type ApiBillingLine = z.infer<typeof BillingLineSchema>;

// `day` is the local day it started on; `hours` is for display, the lines
// are the figures.
const BillingEntrySchema = z.object({
	beat_id: z.string(),
	project_id: z.string(),
	day: z.string(), // YYYY-MM-DD
	start: z.string(), // ISO datetime
	end: z.string(), // ISO datetime
	hours: z.number(),
	billable: z.boolean(),
	overridden: z.boolean(),
	rate_minor: z.number().int().nullable(),
});

export type ApiBillingEntry = z.infer<typeof BillingEntrySchema>;

const ClientBillingSchema = z.object({
	client_id: z.string(),
	name: z.string(),
	archived: z.boolean(),
	currency: z.string(),
	minor_units: z.number().int(),
	running: z.boolean(), // a billable timer is running; it counts once stopped
	billable_hours: z.number(),
	non_billable_hours: z.number(),
	unpriced_hours: z.number(), // the part of billable_hours with no rate
	amount_minor: z.number().int(),
	lines: z.array(BillingLineSchema),
	entries: z.array(BillingEntrySchema),
});

export type ApiClientBilling = z.infer<typeof ClientBillingSchema>;

const CurrencyTotalSchema = z.object({
	currency: z.string(),
	minor_units: z.number().int(),
	billable_hours: z.number(),
	unpriced_hours: z.number(),
	amount_minor: z.number().int(),
});

export type ApiCurrencyTotal = z.infer<typeof CurrencyTotalSchema>;

// A freelance project with finished hours in the month and no client.
const UnattachedHoursSchema = z.object({
	project_id: z.string(),
	name: z.string(),
	hours: z.number(),
});

export type ApiUnattachedHours = z.infer<typeof UnattachedHoursSchema>;

export const BillingMonthSchema = z.object({
	month: z.string(), // YYYY-MM
	first: z.string(), // YYYY-MM-DD
	last: z.string(), // YYYY-MM-DD: the month's end, or today while it runs
	totals: z.array(CurrencyTotalSchema), // one row per currency, never a sum across them
	clients: z.array(ClientBillingSchema),
	unattached: z.array(UnattachedHoursSchema),
});

export type ApiBillingMonth = z.infer<typeof BillingMonthSchema>;

// Report links (docs/billing.md, phase 1c). A link a client opens with no
// login to read its own hours over a fixed range. The owner's side carries
// the token, so a link already sent can be copied again.

export const ApiReportLinkSchema = z.object({
	id: z.string(),
	client_id: z.string(),
	token: z.string(),
	first: z.string(), // YYYY-MM-DD
	last: z.string(), // YYYY-MM-DD
	tz: z.string(), // IANA: the zone the link's days are bucketed in
	show_amounts: z.boolean(),
	show_entries: z.boolean(),
	created_at: z.string(), // ISO datetime
});

export type ApiReportLink = z.infer<typeof ApiReportLinkSchema>;
export const ApiReportLinkListSchema = z.array(ApiReportLinkSchema);

// What the public read answers. A line's rate and amount are null on an
// unpriced run, and on every line when the link does not show amounts; the
// hours are there either way. Deliberately narrower than
// `BillingLineSchema` and `BillingEntrySchema` above — no ids, no source,
// no mark — because the API's public response is narrower.

const ReportLineSchema = z.object({
	project_name: z.string(),
	first: z.string(), // YYYY-MM-DD
	last: z.string(), // YYYY-MM-DD
	hours: z.number(),
	rate_minor: z.number().int().nullable(),
	amount_minor: z.number().int().nullable(),
});

const ReportEntrySchema = z.object({
	day: z.string(), // YYYY-MM-DD, the local day it started on
	start: z.string(), // ISO datetime
	end: z.string(), // ISO datetime
	hours: z.number(),
});

export const ReportSchema = z.object({
	client_name: z.string(),
	first: z.string(), // YYYY-MM-DD
	last: z.string(), // YYYY-MM-DD
	show_amounts: z.boolean(),
	show_entries: z.boolean(),
	currency: z.string().nullable(),
	minor_units: z.number().int().nullable(),
	billable_hours: z.number(),
	unpriced_hours: z.number().nullable(),
	amount_minor: z.number().int().nullable(),
	lines: z.array(ReportLineSchema),
	entries: z.array(ReportEntrySchema),
});

export type ApiReport = z.infer<typeof ReportSchema>;
export type ApiReportLine = z.infer<typeof ReportLineSchema>;
export type ApiReportEntry = z.infer<typeof ReportEntrySchema>;

// Billing budgets (docs/billing.md, phase 1b). These mirror the API's
// `BillingBudgetResponse`, `BillingBudgetRunningResponse` and
// `BillingBudgetStatusResponse`. A budget is addressed by its scope, so it
// has no id; only the limit of its `unit` is set, and `starts_on` only on a
// total. Every figure in a status is the API's, worked out as of today.

const BillingBudgetScopeSchema = z.enum(["client", "project"]);
const BillingBudgetUnitSchema = z.enum(["hours", "money"]);
const BillingBudgetPeriodSchema = z.enum(["monthly", "total"]);

export const ApiBillingBudgetSchema = z.object({
	scope: BillingBudgetScopeSchema,
	scope_id: z.string(),
	client_id: z.string(),
	currency: z.string(), // the client's: a limit_minor is in it
	minor_units: z.number().int(),
	unit: BillingBudgetUnitSchema,
	period: BillingBudgetPeriodSchema,
	limit_hours: z.number().nullable(),
	limit_minor: z.number().int().nullable(),
	starts_on: z.string().nullable(), // YYYY-MM-DD, a total's first day
	warn_at_percent: z.number().int(),
});

export type ApiBillingBudget = z.infer<typeof ApiBillingBudgetSchema>;

// A running timer that counts on the budget, and the UTC instants at which
// it alone would cross the warning and the limit: null once crossed, both
// null when it has no rate under a money budget or another timer counts.
const BillingBudgetRunningSchema = z.object({
	project_id: z.string(),
	since: z.string(), // ISO datetime
	priced: z.boolean(),
	near_at: z.string().nullable(),
	over_at: z.string().nullable(),
});

export type ApiBillingBudgetRunning = z.infer<typeof BillingBudgetRunningSchema>;

const BillingBudgetStatusSchema = z.object({
	scope: BillingBudgetScopeSchema,
	scope_id: z.string(),
	client_id: z.string(),
	name: z.string(), // the client's, or the project's
	active: z.boolean(), // false while its client or project is archived: never alerts
	currency: z.string(),
	minor_units: z.number().int(),
	unit: BillingBudgetUnitSchema,
	period: BillingBudgetPeriodSchema,
	limit_hours: z.number().nullable(),
	limit_minor: z.number().int().nullable(),
	starts_on: z.string().nullable(),
	warn_at_percent: z.number().int(),
	upcoming: z.boolean(), // a total whose first day is after today: no figures yet
	first: z.string(), // YYYY-MM-DD
	last: z.string().nullable(), // a month's end; null on a total
	through: z.string().nullable(), // today; null while upcoming
	billable_hours: z.number(),
	unpriced_hours: z.number(), // the part of billable_hours with no rate
	amount_minor: z.number().int(),
	remaining_hours: z.number().nullable(), // only the unit's own; negative when over
	remaining_minor: z.number().int().nullable(),
	percent_used: z.number().int(), // rounded down, not capped
	state: z.enum(["under", "near", "used_up"]),
	runs_out_on: z.string().nullable(), // YYYY-MM-DD at the recent pace
	running: BillingBudgetRunningSchema.nullable(),
});

export type ApiBillingBudgetStatus = z.infer<typeof BillingBudgetStatusSchema>;
export const ApiBillingBudgetStatusListSchema = z.array(BillingBudgetStatusSchema);

export const ProjectOrganisationSchema = z.object({
	id: z.string(),
	name: z.string(),
	logo_url: z.string().nullable().optional(),
	shared_from: z.string(), // ISO datetime
	// Stage 3: the employer writes the contract, the absences and the
	// adjustments; the member asks for days off.
	contract_managed: z.boolean().optional().default(false),
});

export type ApiProjectOrganisation = z.infer<typeof ProjectOrganisationSchema>;

export const ApiProjectSchema = z.object({
	id: z.string().nullable().optional(),
	name: z.string(),
	description: z.string().nullable().optional(),
	color: z.string().nullable().optional(),
	archived: z.boolean().optional().default(false),
	weekly_goal: z.number().nullable().optional(),
	goal_type: z.enum(["target", "cap"]).optional().default("target"),
	goal_overrides: z.array(GoalOverrideSchema).optional().default([]),
	// P1.1: previously stripped by parseApiResponse — the wire now carries
	// these (P0.1 expanded ProjectResponse), so accept them on the way in.
	github_repo: z.string().nullable().optional(),
	category: z.string().nullable().optional(),
	autostart_repos: z.array(z.string()).optional().default([]),
	// A contract is read only on a day job; on any other kind it is null.
	kind: ProjectKindSchema.optional().default("side_project"),
	contract: ContractSchema.nullable().optional(),
	// The organisation that owns the project, when it is not the reader
	// (docs/organisations.md): its name and logo mark the project in a list,
	// and `shared_from` is the instant from which the reader's hours on it
	// are the organisation's. Null, or absent from an older API, on a
	// personal project.
	organisation: ProjectOrganisationSchema.nullable().optional(),
});

export type ApiProject = z.infer<typeof ApiProjectSchema>;

/**
 * The list-endpoint item — same fields as ApiProject plus optional
 * aggregation slots populated when GET /api/projects/?include=... is sent.
 * P3.0 of the project-management revamp: collapses the previous N+1 fan-out
 * (a total and a week read per project) into one round-trip.
 */
export const ApiProjectListItemSchema = ApiProjectSchema.extend({
	total_minutes: z.number().nullable().optional(),
	weekly_minutes: z.number().nullable().optional(),
	effective_goal: z.number().nullable().optional(),
	effective_goal_type: z.enum(["target", "cap"]).nullable().optional(),
	effective_goal_overridden: z.boolean().nullable().optional(),
	// The current week against the contract, on a day job that has one; what
	// GET /contract/week reports, so the index can show it without a fan-out.
	// Null elsewhere, and all but contract_worked null under an objective term.
	contract_expected: z.number().nullable().optional(),
	contract_worked: z.number().nullable().optional(),
	contract_remaining: z.number().nullable().optional(),
	balance: z.number().nullable().optional(),
	last_tracked_at: z.string().nullable().optional(),
});

export type ApiProjectListItem = z.infer<typeof ApiProjectListItemSchema>;

export const ApiBeatSchema = z.object({
	id: z.string().nullable().optional(),
	start: z.string(), // ISO datetime
	end: z.string().nullable().optional(), // ISO datetime
	project_id: z.string().nullable().optional(),
	note: z.string().nullable().optional(),
	tags: z.array(z.string()).optional().default([]),
	// Set when the entry is an organisation's working-time record: tracked
	// on one of its projects, or shared with it when the project was connected.
	organisation_id: z.string().nullable().optional(),
	// Stage 3: who entered this time for the member, when a decider did.
	entered_by: z.string().nullable().optional(),
});

export type ApiBeat = z.infer<typeof ApiBeatSchema>;

export const TimerStatusSchema = z.object({
	isBeating: z.boolean(),
	project: ApiProjectSchema.nullable().optional(),
	since: z.string().nullable().optional(), // ISO datetime
	so_far: z.string().nullable().optional(), // Duration string like "0:14:25.297277"
});

export type TimerStatus = z.infer<typeof TimerStatusSchema>;

export const HeatmapDaySchema = z.object({
	date: z.string(),
	total_minutes: z.number(),
	session_count: z.number(),
	project_count: z.number(),
});

export type HeatmapDay = z.infer<typeof HeatmapDaySchema>;

export const RhythmSlotSchema = z.object({
	slot: z.number(),
	minutes: z.number(),
});

export type RhythmSlot = z.infer<typeof RhythmSlotSchema>;

export const HeatmapDayListSchema = z.array(HeatmapDaySchema);
export const RhythmSlotListSchema = z.array(RhythmSlotSchema);

/**
 * One flow-state window from the daemon's signal collector. Each window
 * is typically 1 minute of aggregated desktop activity. The composite
 * `flow_score` is a weighted blend of cadence, coherence, and category
 * fit — see the daemon's collector/scorer.go.
 */
export const FlowWindowSchema = z.object({
	id: z.string(),
	window_start: z.string(),
	window_end: z.string(),
	flow_score: z.number(),
	cadence_score: z.number(),
	coherence_score: z.number(),
	category_fit_score: z.number(),
	idle_fraction: z.number(),
	dominant_bundle_id: z.string(),
	dominant_category: z.string(),
	context_switches: z.number(),
	active_project_id: z.string().nullable(),
	editor_repo: z.string().nullable().optional(),
	editor_branch: z.string().nullable().optional(),
	editor_language: z.string().nullable().optional(),
});

export type FlowWindow = z.infer<typeof FlowWindowSchema>;

export const FlowWindowListSchema = z.array(FlowWindowSchema);

/** One bucket inside FlowWindowSummary — the highest-count entry on
 * its grouping axis (top_repo / top_language / top_bundle). */
const FlowTopBucketSchema = z.object({
	key: z.string(),
	avg: z.number(),
	count: z.number(),
});
export type FlowTopBucket = z.infer<typeof FlowTopBucketSchema>;

/** Aggregate stats for a flow-window slice, returned in a single
 * round-trip by GET /api/signals/flow-windows/summary. Mirrors the
 * Python FlowWindowSummaryResponse. */
export const FlowWindowSummarySchema = z.object({
	count: z.number(),
	avg: z.number(),
	peak: z.number(),
	peak_at: z.string().nullable(),
	top_repo: FlowTopBucketSchema.nullable(),
	top_language: FlowTopBucketSchema.nullable(),
	top_bundle: FlowTopBucketSchema.nullable(),
});
export type FlowWindowSummary = z.infer<typeof FlowWindowSummarySchema>;

export const ProductivityScoreSchema = z.object({
	score: z.number(),
	components: z.object({
		consistency: z.number(),
		goals: z.number(),
		quality: z.number(),
	}),
});

export type ProductivityScore = z.infer<typeof ProductivityScoreSchema>;

export const ScoreHistoryItemSchema = z.object({
	week_of: z.string(),
	score: z.number(),
});

export type ScoreHistoryItem = z.infer<typeof ScoreHistoryItemSchema>;

export const ScoreHistorySchema = z.array(ScoreHistoryItemSchema);

const ProjectBreakdownEntrySchema = z.object({
	project_id: z.string(),
	name: z.string(),
	hours: z.number(),
});

export type ProjectBreakdownEntry = z.infer<typeof ProjectBreakdownEntrySchema>;

export const WeeklyDigestSchema = z.object({
	id: z.string().nullable().optional(),
	week_of: z.string(),
	generated_at: z.string(),
	total_hours: z.number(),
	session_count: z.number(),
	active_days: z.number(),
	top_project_id: z.string().nullable().optional(),
	top_project_name: z.string().nullable().optional(),
	top_project_hours: z.number().default(0),
	vs_last_week_pct: z.number().nullable().optional(),
	longest_day: z.string().nullable().optional(),
	longest_day_hours: z.number().default(0),
	best_streak: z.number().default(0),
	observation: z.string().default(""),
	project_breakdown: z.array(ProjectBreakdownEntrySchema).default([]),
	productivity_score: z.number().default(0),
});

export type WeeklyDigest = z.infer<typeof WeeklyDigestSchema>;

export const WeeklyDigestListSchema = z.array(WeeklyDigestSchema);

const InsightCardSchema = z.object({
	id: z.string(),
	type: z.string(),
	title: z.string(),
	body: z.string(),
	data: z.record(z.string(), z.unknown()).default({}),
	priority: z.number().default(3),
});

export type InsightCard = z.infer<typeof InsightCardSchema>;

export const PatternsResponseSchema = z.object({
	insights: z.array(InsightCardSchema),
	generated_at: z.string(),
});

export type PatternsResponse = z.infer<typeof PatternsResponseSchema>;

export const FocusScoreSchema = z.object({
	beat_id: z.string(),
	score: z.number(),
	components: z.object({
		length: z.number(),
		peak_hours: z.number(),
		fragmentation: z.number(),
	}),
});

export type FocusScore = z.infer<typeof FocusScoreSchema>;

export const FocusScoreListSchema = z.array(FocusScoreSchema);

export const ProjectHealthSchema = z.object({
	project_id: z.string(),
	project_name: z.string(),
	days_since_last: z.number().nullable().optional(),
	weekly_goal_trend: z.array(z.number()).default([]),
	avg_session_length_trend: z.array(z.number()).default([]),
	alert: z.string().nullable().optional(),
});

export type ProjectHealth = z.infer<typeof ProjectHealthSchema>;

export const ProjectHealthListSchema = z.array(ProjectHealthSchema);

export const CalendarStatusSchema = z.object({
	connected: z.boolean(),
	provider: z.string().nullable().optional(),
});

export type CalendarStatus = z.infer<typeof CalendarStatusSchema>;

export const GitHubStatusSchema = z.object({
	connected: z.boolean(),
	github_username: z.string().nullable().optional(),
});

export type GitHubStatus = z.infer<typeof GitHubStatusSchema>;

export const GitCommitDaySchema = z.object({
	date: z.string(),
	commit_count: z.number(),
});

export type GitCommitDay = z.infer<typeof GitCommitDaySchema>;

export const GitCommitActivitySchema = z.array(GitCommitDaySchema);

export const GapSchema = z.object({
	start: z.string(),
	end: z.string(),
	duration_minutes: z.number(),
});

export type Gap = z.infer<typeof GapSchema>;

export const GapListSchema = z.array(GapSchema);

// Organisations (docs/organisations.md). These mirror the API's
// `OrganisationResponse`, `MembershipResponse`, `MemberResponse`,
// `InviteResponse`, `InvitationResponse`, `InvitePreviewResponse`,
// `JoinResponse`, `JoinRequestResponse`, `OrgProjectResponse`,
// `AssignmentResponse`, `RecordResponse` and `ArchiveResponse`.

export const OrgRoleSchema = z.enum(["owner", "admin", "manager", "viewer", "member"]);
export type ApiOrgRole = z.infer<typeof OrgRoleSchema>;

export const WeekStartSchema = z.enum(["monday", "saturday", "sunday"]);

export const ApiOrganisationSchema = z.object({
	id: z.string(),
	name: z.string(),
	logo_url: z.string().nullable().optional(),
	week_start: WeekStartSchema.optional().default("monday"),
	holiday_country: z.string().nullable().optional(),
	holiday_subdivision: z.string().nullable().optional(),
	timezone: z.string().optional().default("UTC"),
	created_at: z.string(),
});
export type ApiOrganisation = z.infer<typeof ApiOrganisationSchema>;

export const ApiMembershipSchema = z.object({
	organisation: ApiOrganisationSchema,
	role: OrgRoleSchema,
	joined_at: z.string(),
	left_at: z.string().nullable().optional(),
	left_reason: z.enum(["left", "removed", "erased"]).nullable().optional(),
});
export type ApiMembership = z.infer<typeof ApiMembershipSchema>;
export const ApiMembershipListSchema = z.array(ApiMembershipSchema);

export const ApiMemberSchema = z.object({
	user_id: z.string(),
	name: z.string(),
	email: z.string(),
	role: OrgRoleSchema,
	joined_at: z.string(),
	left_at: z.string().nullable().optional(),
});
export type ApiMember = z.infer<typeof ApiMemberSchema>;
export const ApiMemberListSchema = z.array(ApiMemberSchema);

export const ApiInviteSchema = z.object({
	id: z.string(),
	email: z.string().nullable().optional(),
	role: OrgRoleSchema,
	requires_approval: z.boolean(),
	token: z.string(),
	created_at: z.string(),
	expires_at: z.string(),
	accepted_at: z.string().nullable().optional(),
});
export type ApiInvite = z.infer<typeof ApiInviteSchema>;
export const ApiInviteListSchema = z.array(ApiInviteSchema);

const OrganisationCardSchema = z.object({
	id: z.string(),
	name: z.string(),
	logo_url: z.string().nullable().optional(),
});

export const ApiInvitationSchema = z.object({
	role: OrgRoleSchema,
	expires_at: z.string(),
	organisation: OrganisationCardSchema,
});
export type ApiInvitation = z.infer<typeof ApiInvitationSchema>;
export const ApiInvitationListSchema = z.array(ApiInvitationSchema);

export const ApiInvitePreviewSchema = z.object({
	organisation: OrganisationCardSchema,
	role: OrgRoleSchema,
	requires_approval: z.boolean(),
	addressed: z.boolean(),
	already_member: z.boolean(),
});
export type ApiInvitePreview = z.infer<typeof ApiInvitePreviewSchema>;

export const ApiJoinSchema = z.object({
	status: z.enum(["joined", "pending"]),
	membership: ApiMembershipSchema.nullable().optional(),
});
export type ApiJoin = z.infer<typeof ApiJoinSchema>;

export const ApiJoinRequestSchema = z.object({
	id: z.string(),
	user_id: z.string(),
	name: z.string(),
	email: z.string(),
	requested_at: z.string(),
});
export type ApiJoinRequest = z.infer<typeof ApiJoinRequestSchema>;
export const ApiJoinRequestListSchema = z.array(ApiJoinRequestSchema);

export const ApiAssignmentSchema = z.object({
	user_id: z.string(),
	name: z.string().nullable().optional(),
	shared_from: z.string(),
	assigned_at: z.string(),
	ended_at: z.string().nullable().optional(),
	has_contract: z.boolean(),
});
export type ApiAssignment = z.infer<typeof ApiAssignmentSchema>;

const OrgProjectFieldsSchema = z.object({
	id: z.string(),
	name: z.string(),
	description: z.string().nullable().optional(),
	color: z.string().nullable().optional(),
	archived: z.boolean().optional().default(false),
	kind: ProjectKindSchema.optional().default("side_project"),
	github_repo: z.string().nullable().optional(),
	category: z.string().nullable().optional(),
});

export const ApiOrgProjectSchema = OrgProjectFieldsSchema.extend({
	members: z.array(ApiAssignmentSchema),
});
export type ApiOrgProject = z.infer<typeof ApiOrgProjectSchema>;
export const ApiOrgProjectListSchema = z.array(ApiOrgProjectSchema);

const RecordEntrySchema = z.object({
	id: z.string(),
	day: z.string(),
	start: z.string(),
	end: z.string(),
	hours: z.number(),
	note: z.string().nullable().optional(),
});
export type ApiRecordEntry = z.infer<typeof RecordEntrySchema>;

const RecordAbsenceSchema = z.object({
	date: z.string(),
	type: z.string(),
	half_day: z.boolean(),
});

const MemberBalanceSchema = z.object({
	as_of: z.string(),
	balance: z.number(),
	opening: z.number(),
	worked: z.number(),
	expected_through: z.number(),
	adjusted: z.number(),
});

const MemberTotalsSchema = z.object({
	entries: z.number(),
	hours: z.number(),
	first: z.string().nullable().optional(),
	last: z.string().nullable().optional(),
});

const MemberRecordSchema = z.object({
	user_id: z.string(),
	name: z.string(),
	shared_from: z.string(),
	active: z.boolean(),
	hours: z.number(),
	entries: z.array(RecordEntrySchema),
	absences: z.array(RecordAbsenceSchema),
	has_contract: z.boolean(),
	balance: MemberBalanceSchema.nullable().optional(),
	totals: MemberTotalsSchema,
});
export type ApiMemberRecord = z.infer<typeof MemberRecordSchema>;

export const ApiRecordSchema = z.object({
	organisation: OrganisationCardSchema,
	month: z.string(),
	first: z.string(),
	last: z.string(),
	projects: z.array(
		z.object({
			project: OrgProjectFieldsSchema,
			members: z.array(MemberRecordSchema),
		}),
	),
});
export type ApiRecord = z.infer<typeof ApiRecordSchema>;

// Employment (docs/organisations.md, stages 3 and 4).

export const ApiTeamSchema = z.object({
	id: z.string(),
	name: z.string(),
	member_ids: z.array(z.string()),
});
export type ApiTeam = z.infer<typeof ApiTeamSchema>;
export const ApiTeamListSchema = z.array(ApiTeamSchema);

export const ApiManagedContractSchema = z.object({
	project_id: z.string(),
	user_id: z.string(),
	managed: z.boolean(),
	contract: ContractSchema.nullable().optional(),
});
export type ApiManagedContract = z.infer<typeof ApiManagedContractSchema>;

export const RequestStatusSchema = z.enum(["pending", "approved", "declined"]);

export const ApiAbsenceRequestSchema = z.object({
	id: z.string(),
	project_id: z.string(),
	user_id: z.string(),
	date: z.string(),
	type: z.enum(["vacation", "sick", "other"]),
	half_day: z.boolean(),
	note: z.string().nullable().optional(),
	status: RequestStatusSchema,
	requested_at: z.string(),
	decided_at: z.string().nullable().optional(),
	decided_by: z.string().nullable().optional(),
	comment: z.string().nullable().optional(),
});
export type ApiAbsenceRequest = z.infer<typeof ApiAbsenceRequestSchema>;
export const ApiAbsenceRequestListSchema = z.array(ApiAbsenceRequestSchema);

export const TimesheetStatusSchema = z.enum([
	"submitted",
	"approved",
	"changes_requested",
	"reopened",
]);

const FrozenMonthSchema = z.object({
	worked: z.number(),
	expected: z.number().nullable(),
	balance_end: z.number().nullable(),
	entries: z.number(),
	absence_days: z.number(),
});

export const ApiTimesheetSchema = z.object({
	id: z.string(),
	project_id: z.string(),
	user_id: z.string(),
	month: z.string(), // YYYY-MM-01
	status: TimesheetStatusSchema,
	submitted_at: z.string(),
	decided_at: z.string().nullable().optional(),
	decided_by: z.string().nullable().optional(),
	comment: z.string().nullable().optional(),
	frozen: FrozenMonthSchema.nullable().optional(),
	history: z.array(
		z.object({
			at: z.string(),
			by: z.string(),
			action: TimesheetStatusSchema,
			comment: z.string().nullable().optional(),
		}),
	),
});
export type ApiTimesheet = z.infer<typeof ApiTimesheetSchema>;
export const ApiTimesheetListSchema = z.array(ApiTimesheetSchema);

export const ApiAuditEventSchema = z.object({
	at: z.string(),
	actor_user_id: z.string().nullable().optional(),
	event: z.string(),
	subject_user_id: z.string().nullable().optional(),
	project_id: z.string().nullable().optional(),
	details: z.record(z.string(), z.unknown()),
});
export type ApiAuditEvent = z.infer<typeof ApiAuditEventSchema>;
export const ApiAuditEventListSchema = z.array(ApiAuditEventSchema);

export const ApiArchiveSchema = z.object({
	organisation: OrganisationCardSchema,
	role: OrgRoleSchema,
	joined_at: z.string(),
	left_at: z.string().nullable().optional(),
	hours: z.number(),
	projects: z.array(
		z.object({
			project_id: z.string(),
			name: z.string(),
			color: z.string().nullable().optional(),
			hours: z.number(),
			entries: z.array(RecordEntrySchema),
			absences: z.array(RecordAbsenceSchema).optional().default([]),
		}),
	),
});
export type ApiArchive = z.infer<typeof ApiArchiveSchema>;

// Array schemas for list endpoints

export const ApiProjectListSchema = z.array(ApiProjectListItemSchema);
export const ApiBeatListSchema = z.array(ApiBeatSchema);

// Validation helpers

/**
 * Safely parse API response with a schema, returning parsed data or throwing
 */
export function parseApiResponse<T>(schema: z.ZodSchema<T>, data: unknown): T {
	return schema.parse(data);
}
