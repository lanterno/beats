import { describe, expect, it } from "vitest";
import {
	describeTerm,
	fromPercent,
	isTimeBasedOn,
	termHoursPerDay,
	termHoursPerWeek,
	termOn,
	toPercent,
} from "./contract";
import type { Contract, ContractTerm } from "./types";

describe("term arithmetic", () => {
	it("owes percentage × basis a week, and a fifth of that a day", () => {
		const term: ContractTerm = {
			effectiveFrom: "2026-01-05",
			scheduleType: "part_time",
			fullTimeHours: 42,
			percentage: 0.8,
		};
		expect(termHoursPerWeek(term)).toBe(33.6);
		expect(termHoursPerDay(term)).toBe(6.72);
		expect(describeTerm(term)).toBe("Part time · 80% of 42 h · 33.6 h/week");
	});

	it("takes a custom term's hours as stated and an objective term's as none", () => {
		expect(
			termHoursPerWeek({ effectiveFrom: "2026-01-05", scheduleType: "custom", weeklyHours: 32 }),
		).toBe(32);
		expect(termHoursPerWeek({ effectiveFrom: "2026-01-05", scheduleType: "objective" })).toBeNull();
		expect(termHoursPerDay({ effectiveFrom: "2026-01-05", scheduleType: "objective" })).toBeNull();
	});

	it("round-trips a percent through the fraction the API stores", () => {
		expect(fromPercent(80)).toBe(0.8);
		expect(toPercent(0.8)).toBe(80);
		// 33.33% is not a clean binary fraction either way.
		expect(toPercent(fromPercent(33.33))).toBe(33.33);
		expect(toPercent(1)).toBe(100);
	});
});

describe("termOn", () => {
	const contract: Contract = {
		terms: [
			{ effectiveFrom: "2026-01-05", scheduleType: "full_time", fullTimeHours: 40, percentage: 1 },
			{
				effectiveFrom: "2026-04-01",
				scheduleType: "part_time",
				fullTimeHours: 40,
				percentage: 0.8,
			},
		],
		openingBalanceHours: 0,
	};

	it("picks the latest term starting on or before the day", () => {
		expect(termOn(contract, "2026-03-31")?.percentage).toBe(1);
		// A change on a Wednesday applies from that Wednesday.
		expect(termOn(contract, "2026-04-01")?.percentage).toBe(0.8);
		expect(termOn(contract, "2026-12-31")?.percentage).toBe(0.8);
	});

	it("finds nothing before the first term", () => {
		expect(termOn(contract, "2026-01-04")).toBeUndefined();
	});

	it("does not depend on the terms being in order", () => {
		const reversed: Contract = { ...contract, terms: [...contract.terms].reverse() };
		expect(termOn(reversed, "2026-02-01")?.percentage).toBe(1);
	});
});

describe("isTimeBasedOn", () => {
	it("follows the term in force, the first to come before it, and nothing without a contract", () => {
		const contract: Contract = {
			terms: [
				{
					effectiveFrom: "2026-01-05",
					scheduleType: "full_time",
					fullTimeHours: 40,
					percentage: 1,
				},
				{ effectiveFrom: "2026-04-01", scheduleType: "objective" },
			],
			openingBalanceHours: 0,
		};
		expect(isTimeBasedOn(contract, "2026-01-04")).toBe(true);
		expect(isTimeBasedOn(contract, "2026-02-01")).toBe(true);
		expect(isTimeBasedOn(contract, "2026-04-01")).toBe(false);
		expect(isTimeBasedOn(undefined, "2026-02-01")).toBe(false);
	});
});
