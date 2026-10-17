import type {
	ApiBillableOverride,
	ApiBillingEntry,
	ApiBillingLine,
	ApiBillingMonth,
	ApiBillingTerm,
	ApiClientBilling,
	ApiProjectBilling,
} from "@/shared/api";
import type {
	BillingEntry,
	BillingLine,
	BillingMonth,
	BillingTerm,
	ClientBilling,
	ProjectBilling,
	ProjectBillingInput,
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
