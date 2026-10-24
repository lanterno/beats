import type {
	ApiBillableOverride,
	ApiBillingBudget,
	ApiBillingBudgetStatus,
	ApiBillingEntry,
	ApiBillingLine,
	ApiBillingMonth,
	ApiBillingTerm,
	ApiClientBilling,
	ApiProjectBilling,
	ApiReport,
	ApiReportLink,
} from "@/shared/api";
import type {
	BillingBudget,
	BillingBudgetInput,
	BillingBudgetStatus,
	BillingEntry,
	BillingLine,
	BillingMonth,
	BillingTerm,
	ClientBilling,
	ProjectBilling,
	ProjectBillingInput,
	Report,
	ReportLink,
	ReportLinkInput,
} from "./types";

function toBillingTerm(api: ApiBillingTerm): BillingTerm {
	return {
		effectiveFrom: api.effective_from,
		billable: api.billable,
		rateMinor: api.rate_minor ?? undefined,
	};
}

export function toProjectBilling(api: ApiProjectBilling): ProjectBilling {
	return {
		projectId: api.project_id,
		clientId: api.client_id,
		currency: api.currency,
		minorUnits: api.minor_units,
		terms: api.terms.map(toBillingTerm),
	};
}

/** The write body, `rewrite_past` aside. A term with no rate of its own sends null. */
export function toApiProjectBillingInput(input: ProjectBillingInput) {
	return {
		client_id: input.clientId,
		terms: input.terms.map((term) => ({
			effective_from: term.effectiveFrom,
			billable: term.billable,
			rate_minor: term.rateMinor ?? null,
		})),
	};
}

/** Every mark, by entry id. */
export function toOverrideMap(api: ApiBillableOverride[]): Map<string, boolean> {
	return new Map(api.map((mark) => [mark.beat_id, mark.billable]));
}

function toBillingLine(api: ApiBillingLine): BillingLine {
	return {
		projectId: api.project_id,
		projectName: api.project_name,
		rateMinor: api.rate_minor ?? undefined,
		source: api.source ?? undefined,
		first: api.first,
		last: api.last,
		hours: api.hours,
		amountMinor: api.amount_minor ?? undefined,
	};
}

function toBillingEntry(api: ApiBillingEntry): BillingEntry {
	return {
		beatId: api.beat_id,
		projectId: api.project_id,
		day: api.day,
		start: api.start,
		end: api.end,
		hours: api.hours,
		billable: api.billable,
		overridden: api.overridden,
		rateMinor: api.rate_minor ?? undefined,
	};
}

function toClientBilling(api: ApiClientBilling): ClientBilling {
	return {
		clientId: api.client_id,
		name: api.name,
		archived: api.archived,
		currency: api.currency,
		minorUnits: api.minor_units,
		running: api.running,
		billableHours: api.billable_hours,
		nonBillableHours: api.non_billable_hours,
		unpricedHours: api.unpriced_hours,
		amountMinor: api.amount_minor,
		lines: api.lines.map(toBillingLine),
		entries: api.entries.map(toBillingEntry),
	};
}

export function toBillingMonth(api: ApiBillingMonth): BillingMonth {
	return {
		month: api.month,
		first: api.first,
		last: api.last,
		totals: api.totals.map((total) => ({
			currency: total.currency,
			minorUnits: total.minor_units,
			billableHours: total.billable_hours,
			unpricedHours: total.unpriced_hours,
			amountMinor: total.amount_minor,
		})),
		clients: api.clients.map(toClientBilling),
		unattached: api.unattached.map((item) => ({
			projectId: item.project_id,
			name: item.name,
			hours: item.hours,
		})),
	};
}

export function toBillingBudget(api: ApiBillingBudget): BillingBudget {
	return {
		scope: api.scope,
		scopeId: api.scope_id,
		clientId: api.client_id,
		currency: api.currency,
		minorUnits: api.minor_units,
		unit: api.unit,
		period: api.period,
		limitHours: api.limit_hours ?? undefined,
		limitMinor: api.limit_minor ?? undefined,
		startsOn: api.starts_on ?? undefined,
		warnAtPercent: api.warn_at_percent,
	};
}

export function toBillingBudgetStatus(api: ApiBillingBudgetStatus): BillingBudgetStatus {
	return {
		...toBillingBudget(api),
		name: api.name,
		active: api.active,
		upcoming: api.upcoming,
		first: api.first,
		last: api.last ?? undefined,
		through: api.through ?? undefined,
		billableHours: api.billable_hours,
		unpricedHours: api.unpriced_hours,
		amountMinor: api.amount_minor,
		remainingHours: api.remaining_hours ?? undefined,
		remainingMinor: api.remaining_minor ?? undefined,
		percentUsed: api.percent_used,
		state: api.state,
		runsOutOn: api.runs_out_on ?? undefined,
		running: api.running
			? {
					projectId: api.running.project_id,
					since: api.running.since,
					priced: api.running.priced,
					nearAt: api.running.near_at ?? undefined,
					overAt: api.running.over_at ?? undefined,
				}
			: undefined,
	};
}

/**
 * The write body: every key the API requires, the other unit's limit and a
 * monthly budget's `starts_on` sent as null.
 */
export function toApiBillingBudgetInput(input: BillingBudgetInput) {
	return {
		unit: input.unit,
		period: input.period,
		limit_hours: input.unit === "hours" ? (input.limitHours ?? null) : null,
		limit_minor: input.unit === "money" ? (input.limitMinor ?? null) : null,
		starts_on: input.period === "total" ? (input.startsOn ?? null) : null,
		warn_at_percent: input.warnAtPercent,
	};
}

/** A report link as its owner sees it, token included. */
export function toReportLink(api: ApiReportLink): ReportLink {
	return {
		id: api.id,
		clientId: api.client_id,
		token: api.token,
		first: api.first,
		last: api.last,
		tz: api.tz,
		showAmounts: api.show_amounts,
		showEntries: api.show_entries,
		createdAt: api.created_at,
	};
}

/** The write body: every key the API requires. */
export function toApiReportLinkInput(input: ReportLinkInput) {
	return {
		first: input.first,
		last: input.last,
		tz: input.tz,
		show_amounts: input.showAmounts,
		show_entries: input.showEntries,
	};
}

/**
 * What a report link serves. Every money figure arrives null when the link
 * hides amounts, and becomes `undefined` here, so a component asks
 * `amountMinor === undefined` rather than distinguishing two empties.
 */
export function toReport(api: ApiReport): Report {
	return {
		clientName: api.client_name,
		first: api.first,
		last: api.last,
		showAmounts: api.show_amounts,
		showEntries: api.show_entries,
		currency: api.currency ?? undefined,
		minorUnits: api.minor_units ?? undefined,
		billableHours: api.billable_hours,
		unpricedHours: api.unpriced_hours ?? undefined,
		amountMinor: api.amount_minor ?? undefined,
		lines: api.lines.map((line) => ({
			projectName: line.project_name,
			first: line.first,
			last: line.last,
			hours: line.hours,
			rateMinor: line.rate_minor ?? undefined,
			amountMinor: line.amount_minor ?? undefined,
		})),
		entries: api.entries.map((entry) => ({
			day: entry.day,
			start: entry.start,
			end: entry.end,
			hours: entry.hours,
		})),
	};
}
