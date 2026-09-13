import { describe, expect, it } from "vitest";
import { describeLedgerNote, ledgerCsv, ledgerRows } from "./ledger";
import type { Contract, Ledger, LedgerNote, LedgerWeek } from "./types";

// Today is Thu Sep 10, 2026: the current week is Sep 7 and never in the rows.
const TODAY = "2026-09-10";

function week(weekOf: string, patch: Partial<LedgerWeek> = {}): LedgerWeek {
	return {
		weekOf,
		worked: 33.6,
		days: [6.72, 6.72, 6.72, 6.72, 6.72, 0, 0],
		effectiveGoal: 33.6,
		effectiveGoalType: "target",
		effectiveGoalOverridden: false,
		contractExpected: 33.6,
		balanceEnd: 5,
		notes: [],
		...patch,
	};
}

function ledger(weeks: LedgerWeek[], extra: Partial<Ledger> = {}): Ledger {
	return {
		since: "2026-01-05",
		totals: { expected: 840, worked: 848.5, balance: 8.5 },
		weeks,
		...extra,
	};
}

// The mockup's contract: 60% from Jan 5, 80% from Aug 3, full time planned from Jan 4, 2027.
const CONTRACT: Contract = {
	terms: [
		{ effectiveFrom: "2026-01-05", scheduleType: "part_time", fullTimeHours: 42, percentage: 0.6 },
		{
			effectiveFrom: "2026-08-03",
			scheduleType: "part_time",
			fullTimeHours: 42,
			percentage: 0.8,
			note: "Four days a week from August",
		},
		{ effectiveFrom: "2027-01-04", scheduleType: "full_time", fullTimeHours: 42, percentage: 1 },
	],
	openingBalanceHours: 2,
};
const DAY_JOB = { kind: "day_job" as const, contract: CONTRACT };

/** Where each row sits: a rule by its kind and date, so placement tests do not pin the copy. */
function shape(rows: ReturnType<typeof ledgerRows>): string[] {
	return rows.map((r) => {
		if (r.type === "week") return `week ${r.week.weekOf}`;
		if (r.type === "rule") return `rule ${r.rule} ${r.date}${r.planned ? " planned" : ""}`;
		return `quiet ${r.text}`;
	});
}

describe("ledgerRows: rule rows", () => {
	it("puts a term's rule under the week its date falls in, a planned one on top, and drops the current week", () => {
		const rows = ledgerRows(
			ledger([week("2026-09-07"), week("2026-08-31"), week("2026-08-03"), week("2026-07-27")]),
			DAY_JOB,
			TODAY,
		);
		expect(shape(rows)).toEqual([
			"rule term 2027-01-04 planned",
			"week 2026-08-31",
			"week 2026-08-03",
			"rule term 2026-08-03",
			"week 2026-07-27",
		]);
		const change = rows[3];
		expect(change).toMatchObject({
			text: "From Mon Aug 3, 2026 · Part time 80% of 42 h = 33.6 h/wk",
			sub: "was 60% · 25.2 h · “Four days a week from August”",
		});
		expect(rows[0]).toMatchObject({
			text: "From Mon Jan 4, 2027 · Full time · 42 h/wk · planned",
			sub: "was 80% · 33.6 h",
		});
	});

	it("says the weekday of a mid-week change", () => {
		const contract: Contract = {
			...CONTRACT,
			terms: [
				CONTRACT.terms[0],
				{ ...CONTRACT.terms[1], effectiveFrom: "2026-08-05", note: undefined },
			],
		};
		const rows = ledgerRows(
			ledger([week("2026-09-07"), week("2026-08-03"), week("2026-07-27")]),
			{ kind: "day_job", contract },
			TODAY,
		);
		expect(shape(rows)).toEqual(["week 2026-08-03", "rule term 2026-08-05", "week 2026-07-27"]);
		expect(rows[1]).toMatchObject({
			text: "From Wed Aug 5, 2026 · Part time 80% of 42 h = 33.6 h/wk",
			sub: "was 60% · 25.2 h",
		});
	});

	it("opens the ledger with the contract's start once the rows reach it, a Saturday start included", () => {
		const contract: Contract = {
			terms: [{ effectiveFrom: "2026-01-10", scheduleType: "custom", weeklyHours: 32 }],
			openingBalanceHours: 2,
		};
		// The week of Jan 5 holds the Saturday; it expects nothing (before the
		// contract on both counts) and the rule sits under it.
		const rows = ledgerRows(
			ledger([
				week("2026-01-19"),
				week("2026-01-12", { contractExpected: 32, balanceEnd: 2.5 }),
				week("2026-01-05", { worked: 3, contractExpected: null, balanceEnd: null }),
			]),
			{ kind: "day_job", contract },
			"2026-01-22",
		);
		expect(shape(rows)).toEqual(["week 2026-01-12", "week 2026-01-05", "rule opening 2026-01-10"]);
		expect(rows[2]).toMatchObject({
			text: "Contract starts Sat Jan 10, 2026 · Custom · 32 h/wk",
			sub: "brought forward +2.0 h",
		});
	});

	it("does not show a rule the rows have not reached", () => {
		const rows = ledgerRows(ledger([week("2026-09-07"), week("2026-08-31")]), DAY_JOB, TODAY);
		expect(shape(rows)).toEqual(["rule term 2027-01-04 planned", "week 2026-08-31"]);
	});

	it("closes the ledger above the week the contract ended in, with the frozen balance", () => {
		const contract: Contract = {
			...CONTRACT,
			terms: CONTRACT.terms.slice(0, 2),
			endedOn: "2026-08-26",
		};
		const rows = ledgerRows(
			ledger(
				[
					week("2026-09-07"),
					week("2026-08-31", { contractExpected: 0, balanceEnd: 5.7 }),
					week("2026-08-24", { contractExpected: 20.16, balanceEnd: 5.7 }),
					week("2026-08-17"),
				],
				{ totals: { expected: 800, worked: 805.7, balance: 5.7 } },
			),
			{ kind: "day_job", contract },
			TODAY,
		);
		expect(shape(rows)).toEqual([
			"week 2026-08-31",
			"rule ended 2026-08-26",
			"week 2026-08-24",
			"week 2026-08-17",
		]);
		expect(rows[1]).toMatchObject({ text: "Ended Wed Aug 26, 2026 · final balance +5.7 h" });
	});

	it("has no rules on a project the contract does not govern", () => {
		const rows = ledgerRows(
			ledger([week("2026-09-07"), week("2026-08-31")], { since: null, totals: null }),
			{ kind: "side_project" },
			TODAY,
		);
		expect(shape(rows)).toEqual(["week 2026-08-31"]);
	});
});

describe("ledgerRows: the quiet collapse", () => {
	const quiet = (weekOf: string, notes: LedgerNote[] = []) =>
		week(weekOf, { worked: 0, days: [0, 0, 0, 0, 0, 0, 0], contractExpected: 0, notes });
	const vacation = (date: string): LedgerNote => ({ date, kind: "vacation", halfDay: false });

	it("folds two or more empty weeks in a row, and names a vacation as away", () => {
		const rows = ledgerRows(
			ledger([
				week("2026-09-07"),
				week("2026-07-27"),
				quiet("2026-07-20", [vacation("2026-07-20")]),
				quiet("2026-07-13", [vacation("2026-07-13")]),
				quiet("2026-07-06", [vacation("2026-07-06")]),
				week("2026-06-29"),
			]),
			{ kind: "day_job", contract: { ...CONTRACT, terms: CONTRACT.terms.slice(0, 1) } },
			TODAY,
		);
		expect(shape(rows)).toEqual([
			"week 2026-07-27",
			"quiet ·· 3 weeks away · Jul 6 – 26 · vacation ··",
			"week 2026-06-29",
		]);
		const run = rows[1];
		expect(run.type === "quiet" && run.weeks.map((w) => w.weekOf)).toEqual([
			"2026-07-20",
			"2026-07-13",
			"2026-07-06",
		]);
	});

	it("calls a run away only when every note is a vacation", () => {
		const rows = ledgerRows(
			ledger([
				week("2026-09-07"),
				quiet("2026-07-20", [vacation("2026-07-20")]),
				quiet("2026-07-13", [{ date: "2026-07-13", kind: "sick", halfDay: false }]),
				quiet("2026-07-06", [vacation("2026-07-06")]),
			]),
			{ kind: "day_job", contract: { ...CONTRACT, terms: CONTRACT.terms.slice(0, 1) } },
			TODAY,
		);
		expect(shape(rows)).toEqual(["quiet ·· 3 quiet weeks ··"]);
	});

	it("calls a run without notes quiet, and leaves a run of one as a row", () => {
		const rows = ledgerRows(
			ledger([
				week("2026-09-07"),
				quiet("2026-08-31"),
				week("2026-08-24"),
				quiet("2026-08-17"),
				quiet("2026-08-10", [{ date: "2026-08-10", kind: "sick", halfDay: false }]),
			]),
			{ kind: "day_job", contract: { ...CONTRACT, terms: CONTRACT.terms.slice(0, 1) } },
			TODAY,
		);
		expect(shape(rows)).toEqual([
			"week 2026-08-31",
			"week 2026-08-24",
			"quiet ·· 2 quiet weeks ··",
		]);
	});

	it("does not fold across a rule row, nor a side project's week that missed a goal or overrides it", () => {
		const side = (weekOf: string, patch: Partial<LedgerWeek> = {}) =>
			week(weekOf, {
				worked: 0,
				days: [0, 0, 0, 0, 0, 0, 0],
				contractExpected: null,
				balanceEnd: null,
				effectiveGoal: null,
				...patch,
			});
		const sideRows = (weeks: LedgerWeek[]) =>
			shape(
				ledgerRows(
					ledger([week("2026-09-07"), ...weeks], { since: null, totals: null }),
					{ kind: "side_project" },
					TODAY,
				),
			);
		// Nothing to show on either: they fold.
		expect(sideRows([side("2026-08-31"), side("2026-08-24")])).toEqual([
			"quiet ·· 2 quiet weeks ··",
		]);
		// An 8 h goal missed is a −8.0; a "No goal" override keeps the cell it is removed from.
		expect(
			sideRows([
				side("2026-08-31", { effectiveGoal: 8 }),
				side("2026-08-24", { effectiveGoalOverridden: true }),
				side("2026-08-17", { effectiveGoalOverridden: true }),
			]),
		).toEqual(["week 2026-08-31", "week 2026-08-24", "week 2026-08-17"]);

		const split = ledgerRows(
			ledger([week("2026-09-07"), quiet("2026-08-03"), quiet("2026-07-27")]),
			DAY_JOB,
			TODAY,
		);
		expect(shape(split)).toEqual([
			"rule term 2027-01-04 planned",
			"week 2026-08-03",
			"rule term 2026-08-03",
			"week 2026-07-27",
		]);
	});
});

describe("ledgerRows: the +/− cell", () => {
	it("reads the move between two closes when it has both, else worked − expected, else worked − goal", () => {
		const rows = ledgerRows(
			ledger([
				week("2026-09-07"),
				// The contract ended mid-week: 10 h worked, 0 expected, but the close did not move.
				week("2026-08-31", { worked: 10, contractExpected: 0, balanceEnd: 5.7 }),
				week("2026-08-24", { worked: 32.9, contractExpected: 33.6, balanceEnd: 5.7 }),
				week("2026-08-17", { worked: 35.1, contractExpected: 33.6, balanceEnd: 6.4 }),
			]),
			DAY_JOB,
			TODAY,
		);
		const deltas = rows.map((r) => (r.type === "week" ? r.delta : "-"));
		// The oldest row has no close before it and falls back to the arithmetic.
		expect(deltas).toEqual(["-", 0, -0.7, 1.5]);

		const side = ledgerRows(
			ledger(
				[
					week("2026-09-07"),
					week("2026-08-31", {
						worked: 8.4,
						contractExpected: null,
						balanceEnd: null,
						effectiveGoal: 8,
					}),
					week("2026-08-24", {
						worked: 3,
						contractExpected: null,
						balanceEnd: null,
						effectiveGoal: null,
					}),
				],
				{ since: null, totals: null },
			),
			{ kind: "side_project" },
			TODAY,
		);
		expect(side.map((r) => (r.type === "week" ? r.delta : "-"))).toEqual([0.4, null]);
	});

	it("moves the contract's first close from the opening balance, whatever was logged before it", () => {
		// Starts Wed Aug 5 with +2.0 h brought forward. Mon and Tue carry 8 h
		// logged before the start; Wed–Fri 18 h against 18 h: the close stays +2.0.
		const wednesday: Contract = {
			terms: [{ effectiveFrom: "2026-08-05", scheduleType: "custom", weeklyHours: 30 }],
			openingBalanceHours: 2,
		};
		const mid = ledgerRows(
			ledger(
				[
					week("2026-09-07"),
					week("2026-08-10", { worked: 30, contractExpected: 30, balanceEnd: 2 }),
					week("2026-08-03", { worked: 26, contractExpected: 18, balanceEnd: 2 }),
					week("2026-07-27", {
						worked: 4,
						effectiveGoal: null,
						contractExpected: null,
						balanceEnd: null,
					}),
				],
				{ since: "2026-08-05" },
			),
			{ kind: "day_job", contract: wednesday },
			TODAY,
		);
		expect(mid.flatMap((r) => (r.type === "week" ? [[r.week.weekOf, r.delta]] : []))).toEqual([
			["2026-08-10", 0],
			["2026-08-03", 0],
			["2026-07-27", null],
		]);

		// Starts Sat Jan 10: its week has no close, and the 3 h worked that
		// Saturday move the next week's, from +2.0 to +6.0.
		const saturday: Contract = {
			terms: [{ effectiveFrom: "2026-01-10", scheduleType: "custom", weeklyHours: 32 }],
			openingBalanceHours: 2,
		};
		const weekend = ledgerRows(
			ledger(
				[
					week("2026-01-19"),
					week("2026-01-12", { worked: 33, contractExpected: 32, balanceEnd: 6 }),
					week("2026-01-05", {
						worked: 3,
						effectiveGoal: null,
						contractExpected: null,
						balanceEnd: null,
					}),
				],
				{ since: "2026-01-10" },
			),
			{ kind: "day_job", contract: saturday },
			"2026-01-22",
		);
		expect(weekend.flatMap((r) => (r.type === "week" ? [r.delta] : []))).toEqual([4, null]);
	});
});

describe("describeLedgerNote", () => {
	it("dates the day and says what it was, a half day marked", () => {
		expect(describeLedgerNote({ date: "2026-08-18", kind: "sick", halfDay: true })).toBe(
			"Tue Aug 18 · sick ½",
		);
		expect(
			describeLedgerNote({
				date: "2026-05-25",
				kind: "holiday",
				halfDay: false,
				name: "Whit Monday",
			}),
		).toBe("Mon May 25 · Whit Monday");
	});
});

describe("ledgerCsv", () => {
	it("writes the header, one line a week with blanks for nulls, and escapes a rule's note", () => {
		const contract: Contract = {
			...CONTRACT,
			terms: [CONTRACT.terms[0], { ...CONTRACT.terms[1], note: 'Four days, "Fridays off"' }],
		};
		const rows = ledgerRows(
			ledger([
				week("2026-09-07"),
				week("2026-08-31", { worked: 32.9, balanceEnd: 5.7 }),
				week("2026-08-03", { worked: 33.6, balanceEnd: 6.4 }),
				week("2026-07-27", {
					worked: 27.1,
					contractExpected: null,
					balanceEnd: null,
					effectiveGoal: null,
				}),
			]),
			{ kind: "day_job", contract },
			TODAY,
		);
		expect(ledgerCsv(rows)).toBe(
			[
				"week,expected,worked,delta,balance",
				"2026-08-31,33.6,32.9,-0.7,5.7",
				"2026-08-03,33.6,33.6,0,6.4",
				'"From Mon Aug 3, 2026 · Part time 80% of 42 h = 33.6 h/wk · was 60% · 25.2 h · “Four days, ""Fridays off""”",,,,',
				"2026-07-27,,27.1,,",
				"",
			].join("\n"),
		);
	});
});
