/**
 * Whether an entry is billable: `in_force_on` and the flag half of
 * `resolve_entry` in `api/src/beats/domain/billing.py`, a second time, so a
 * session row's pill says what the month's report counts. A rule
 * implemented twice, so `resolve.test.ts` repeats the API's cases. Only the
 * flag: the rate and every amount are the API's, and this never prices.
 */

import { parseUtcIso } from "@/shared/lib";
import type { ProjectBilling } from "./types";

/**
 * The term in force on a day: the one with the latest `effectiveFrom` on or
 * before it, as `Contract.term_on` and `termOn`. Undefined before the first:
 * a level says nothing before it starts. Terms come ascending from the API,
 * but a list under edit may not be, so this does not rely on order.
 */
export function inForceOn<T extends { effectiveFrom: string }>(
	terms: readonly T[],
	isoDay: string,
): T | undefined {
	let found: T | undefined;
	for (const term of terms) {
		if (term.effectiveFrom <= isoDay && (!found || term.effectiveFrom > found.effectiveFrom)) {
			found = term;
		}
	}
	return found;
}

/** The calendar day an instant falls on in `tz`, as 'YYYY-MM-DD'. */
function localDay(iso: string, tz: string): string {
	const parts = new Intl.DateTimeFormat("en-US", {
		timeZone: tz,
		year: "numeric",
		month: "2-digit",
		day: "2-digit",
	}).formatToParts(parseUtcIso(iso));
	const part = (type: Intl.DateTimeFormatPartTypes) =>
		parts.find((p) => p.type === type)?.value ?? "";
	return `${part("year")}-${part("month")}-${part("day")}`;
}

export interface EntryBillable {
	billable: boolean;
	/** A mark of the user's decides it, not the project's term — the API's `overridden`. */
	overridden: boolean;
}

/**
 * An entry of a billed project: its mark if it has one, else the project's
 * term in force on the local day it started in `tz`, else not billable. The
 * day is the start's, whole, as the report buckets it — `tz` is the one the
 * page sends the API.
 */
export function entryBillable(
	entry: { id: string; startTime: string },
	billing: ProjectBilling,
	overrides: ReadonlyMap<string, boolean>,
	tz: string,
): EntryBillable {
	const mark = overrides.get(entry.id);
	if (mark !== undefined) return { billable: mark, overridden: true };
	const term = inForceOn(billing.terms, localDay(entry.startTime, tz));
	return { billable: term?.billable ?? false, overridden: false };
}
