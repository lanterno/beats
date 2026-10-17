/**
 * Whether an entry is billable, the rule `api/src/beats/domain/billing.py`
 * applies (`in_force_on`, `resolve_entry`) a second time: the entry's mark,
 * else the project's term in force on the local day it started, else not
 * billable. The cases are those of `api/src/beats/test_billing.py`, on the
 * same dates — Studio Kite's Website, read in Berlin — so a pill on a
 * session row says what the month's report counts. Only the flag is
 * mirrored; every rate and amount is the API's.
 */
import { describe, expect, it } from "vitest";
import { entryBillable, inForceOn } from "./resolve";
import type { BillingTerm, ProjectBilling } from "./types";

const BERLIN = "Europe/Berlin";
const LOS_ANGELES = "America/Los_Angeles";

function billing(...terms: BillingTerm[]): ProjectBilling {
	return { projectId: "p1", clientId: "c1", currency: "EUR", minorUnits: 2, terms };
}

const term = (effectiveFrom: string, billable = true, rateMinor?: number): BillingTerm => ({
	effectiveFrom,
	billable,
	rateMinor,
});

/** A session starting at 09:00 Berlin time (summer time) on `day`. */
const at9 = (id: string, day: string) => ({ id, startTime: `${day}T07:00:00Z` });

const NONE = new Map<string, boolean>();

describe("inForceOn", () => {
	const terms = [term("2026-01-01"), term("2026-10-10", false)];

	it("is the latest term starting on or before the day", () => {
		expect(inForceOn(terms, "2026-10-09")).toBe(terms[0]);
		expect(inForceOn(terms, "2026-10-10")).toBe(terms[1]);
		expect(inForceOn(terms, "2026-12-31")).toBe(terms[1]);
	});

	it("is nothing before the first term: a level says nothing before it starts", () => {
		expect(inForceOn(terms, "2025-12-31")).toBeUndefined();
	});

	it("does not rely on the order of a list under edit", () => {
		expect(inForceOn([...terms].reverse(), "2026-10-11")).toBe(terms[1]);
	});
});

describe("entryBillable", () => {
	it("is not billable before the project's first term", () => {
		const b = billing(term("2026-10-10"));
		expect(entryBillable(at9("early", "2026-10-05"), b, NONE, BERLIN)).toEqual({
			billable: false,
			overridden: false,
		});
		expect(entryBillable(at9("late", "2026-10-12"), b, NONE, BERLIN)).toEqual({
			billable: true,
			overridden: false,
		});
	});

	it("bills an entry marked true before the first term", () => {
		const b = billing(term("2026-10-10", true, 9500));
		expect(
			entryBillable(at9("early", "2026-10-05"), b, new Map([["early", true]]), BERLIN),
		).toEqual({ billable: true, overridden: true });
	});

	it("drops an entry marked false under a billable term", () => {
		const b = billing(term("2026-01-01"));
		const marks = new Map([["dropped", false]]);
		expect(entryBillable(at9("kept", "2026-10-02"), b, marks, BERLIN)).toEqual({
			billable: true,
			overridden: false,
		});
		expect(entryBillable(at9("dropped", "2026-10-03"), b, marks, BERLIN)).toEqual({
			billable: false,
			overridden: true,
		});
	});

	it("stops at a term that is not billable, and leaves the days before it alone", () => {
		const b = billing(term("2026-01-01"), term("2026-11-01", false));
		expect(entryBillable(at9("oct", "2026-10-30"), b, NONE, BERLIN).billable).toBe(true);
		expect(entryBillable(at9("nov", "2026-11-02"), b, NONE, BERLIN).billable).toBe(false);
	});

	it("reads the day in the timezone it is given, not in UTC", () => {
		// 22:30 UTC on 30 September is 00:30 on 1 October in Berlin.
		const late = { id: "b", startTime: "2026-09-30T22:30:00Z" };
		const fromOctober = billing(term("2026-10-01"));
		expect(entryBillable(late, fromOctober, NONE, BERLIN).billable).toBe(true);
		expect(entryBillable(late, fromOctober, NONE, "UTC").billable).toBe(false);
	});

	it("keeps the night US summer time ends in October in Los Angeles", () => {
		// 03:00 UTC on 1 November is 20:00 PDT on 31 October.
		const evening = { id: "b", startTime: "2026-11-01T03:00:00Z" };
		const stopsInNovember = billing(term("2026-01-01"), term("2026-11-01", false));
		expect(entryBillable(evening, stopsInNovember, NONE, LOS_ANGELES).billable).toBe(true);
	});
});
