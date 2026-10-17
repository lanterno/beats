/**
 * Copying last year's company days into the next: each moves to the same
 * month and day, a day on a weekend is still copied, and one is left out —
 * with its reason — on a date already a company day's, on a public holiday,
 * or on 29 February into a year without one.
 */
import { describe, expect, it } from "vitest";
import { copyCompanyDays, describeCompanyDaysCopy, hasCompanyDaysIn } from "./companyHolidays";

const NONE = new Set<string>();

describe("copyCompanyDays", () => {
	it("copies nothing from a year without company days", () => {
		const days = [{ date: "2026-12-24", name: "Christmas Eve" }];
		expect(copyCompanyDays(days, 2026, NONE)).toEqual({ copied: [], skipped: [] });
		expect(copyCompanyDays([], 2026, NONE)).toEqual({ copied: [], skipped: [] });
	});

	it("moves last year's days to the same month and day, by date, names kept", () => {
		const days = [
			{ date: "2025-12-31", name: "New Year's Eve" },
			{ date: "2024-12-24", name: "Two years back" },
			{ date: "2025-12-24", name: "Christmas Eve" },
		];
		expect(copyCompanyDays(days, 2026, NONE)).toEqual({
			copied: [
				{ date: "2026-12-24", name: "Christmas Eve" },
				{ date: "2026-12-31", name: "New Year's Eve" },
			],
			skipped: [],
		});
	});

	it("copies a day that now falls on a weekend", () => {
		// Fri Oct 31, 2025 → Sat Oct 31, 2026: the row says it owes nothing.
		const days = [{ date: "2025-10-31", name: "Bridge day" }];
		expect(copyCompanyDays(days, 2026, NONE).copied).toEqual([
			{ date: "2026-10-31", name: "Bridge day" },
		]);
	});

	it("leaves out 29 February in a year without one, and keeps the 28th the 28th", () => {
		const days = [
			{ date: "2028-02-28", name: "Eve of the leap day" },
			{ date: "2028-02-29", name: "Leap day" },
		];
		expect(copyCompanyDays(days, 2029, NONE)).toEqual({
			copied: [{ date: "2029-02-28", name: "Eve of the leap day" }],
			skipped: [{ date: "2028-02-29", name: "Leap day", reason: "no_such_day" }],
		});
	});

	it("copies 28 February into a leap year as the 28th", () => {
		const days = [{ date: "2027-02-28", name: "Founders' day" }];
		expect(copyCompanyDays(days, 2028, NONE).copied).toEqual([
			{ date: "2028-02-28", name: "Founders' day" },
		]);
	});

	it("leaves out a date that already has a company day, saved or copied before it", () => {
		const days = [
			{ date: "2025-12-24", name: "Christmas Eve" },
			{ date: "2025-12-24", name: "Christmas Eve, twice" },
			{ date: "2025-12-31", name: "New Year's Eve" },
			{ date: "2026-12-31", name: "Silvester" },
		];
		expect(copyCompanyDays(days, 2026, NONE)).toEqual({
			copied: [{ date: "2026-12-24", name: "Christmas Eve" }],
			skipped: [
				{ date: "2025-12-24", name: "Christmas Eve, twice", reason: "taken" },
				{ date: "2025-12-31", name: "New Year's Eve", reason: "taken" },
			],
		});
	});

	it("leaves out a day that is now a public holiday", () => {
		const days = [{ date: "2025-05-29", name: "Ascension bridge" }];
		expect(copyCompanyDays(days, 2026, new Set(["2026-05-29"]))).toEqual({
			copied: [],
			skipped: [{ date: "2025-05-29", name: "Ascension bridge", reason: "public_holiday" }],
		});
	});

	it("passes over a row still without a date", () => {
		const days = [
			{ date: "", name: "Not dated yet" },
			{ date: "2025-12-24", name: "Christmas Eve" },
		];
		expect(copyCompanyDays(days, 2026, NONE).copied).toEqual([
			{ date: "2026-12-24", name: "Christmas Eve" },
		]);
	});
});

describe("hasCompanyDaysIn", () => {
	it("is true only for a year with a dated company day", () => {
		const days = [
			{ date: "", name: "Not dated yet" },
			{ date: "2025-12-24", name: "Christmas Eve" },
		];
		expect(hasCompanyDaysIn(days, 2025)).toBe(true);
		expect(hasCompanyDaysIn(days, 2026)).toBe(false);
		expect(hasCompanyDaysIn([], 2025)).toBe(false);
	});
});

describe("describeCompanyDaysCopy", () => {
	it("says how many were copied, and that they still need saving", () => {
		const copy = { copied: [{ date: "2026-12-24", name: "Christmas Eve" }], skipped: [] };
		expect(describeCompanyDaysCopy(copy, 2026)).toBe("Copied 1 day from 2025 — save to keep it.");
	});

	it("names each day left out and why", () => {
		const copy = copyCompanyDays(
			[
				{ date: "2028-02-29", name: "Leap day" },
				{ date: "2028-12-24", name: "Christmas Eve" },
				{ date: "2028-12-25", name: "Firm Christmas" },
				{ date: "2028-12-31", name: "New Year's Eve" },
				{ date: "2029-12-31", name: "Silvester" },
			],
			2029,
			new Set(["2029-12-25"]),
		);
		expect(describeCompanyDaysCopy(copy, 2029)).toBe(
			"Copied 1 day from 2028 — save to keep it. Left out: Feb 29, 2029 has none · " +
				"Dec 25, already a public holiday · Dec 31, already a company day.",
		);
	});

	it("says nothing was copied when every day was left out", () => {
		const copy = copyCompanyDays(
			[
				{ date: "2025-12-24", name: "Christmas Eve" },
				{ date: "2026-12-24", name: "Christmas Eve" },
			],
			2026,
			NONE,
		);
		expect(describeCompanyDaysCopy(copy, 2026)).toBe(
			"Nothing copied from 2025. Left out: Dec 24, already a company day.",
		);
	});
});
