import { describe, expect, it } from "vitest";
import { describeLedgerNote, ledgerCsv, ledgerRows } from "./ledger";
import type { Contract, Ledger, LedgerAdjustment, LedgerNote, LedgerWeek } from "./types";

// Today is Thu Sep 10, 2026: the current week is Sep 7 and never in the rows.
const TODAY = "2026-09-10";

function week(weekOf: string, patch: Partial<LedgerWeek> = {}): LedgerWeek {
	const row = {
		weekOf,
		worked: 33.6,
		days: [6.72, 6.72, 6.72, 6.72, 6.72, 0, 0],
		effectiveGoal: 33.6,
		effectiveGoalType: "target" as const,
		effectiveGoalOverridden: false,
		contractExpected: 33.6,
		balanceEnd: 5,
		notes: [],
		adjustments: [],
		...patch,
	};
	// The API's move on a full week of the contract, null exactly when the
	// close is; a week a contract starts or ends in sends its own.
	const moved =
		row.balanceEnd === null || row.contractExpected === null
			? null
			: Math.round((row.worked - row.contractExpected) * 100) / 100;
	return { balanceMoved: moved, ...row };
}

function ledger(weeks: LedgerWeek[], extra: Partial<Ledger> = {}): Ledger {
	return {
		since: "2026-01-05",
		totals: { expected: 840, worked: 848.5, adjusted: 0, balance: 8.5 },
		endedBalance: null,
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
	companyHolidays: [],
	holidaysNotGiven: [],
};
const DAY_JOB = { kind: "day_job" as const, contract: CONTRACT };

/** Where each row sits: a rule by its kind and date, so placement tests do not pin the copy. */
function shape(rows: ReturnType<typeof ledgerRows>): string[] {
	return rows.map((r) => {
		if (r.type === "week") return `week ${r.week.weekOf}`;
		if (r.type === "rule") return `rule ${r.rule} ${r.date}${r.planned ? " planned" : ""}`;
		if (r.type === "adjustment") return `adjustment ${r.adjustment.date}`;
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
			companyHolidays: [],
			holidaysNotGiven: [],
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
				{
					totals: { expected: 800, worked: 805.7, adjusted: 0, balance: 5.7 },
					endedBalance: 5.7,
				},
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

	it("says the contract ended on its last day, without a final balance while its hours count", () => {
		// Read on the end day: its hours still count, so the API's
		// `endedBalance` is null and today's balance is not the close either.
		const contract: Contract = {
			...CONTRACT,
			terms: CONTRACT.terms.slice(0, 2),
			endedOn: "2026-08-26",
		};
		const rows = ledgerRows(
			ledger([week("2026-08-24"), week("2026-08-17")]),
			{ kind: "day_job", contract },
			"2026-08-26",
		);
		expect(shape(rows)).toEqual(["rule ended 2026-08-26", "week 2026-08-17"]);
		// "Ended", as the header and the register say that day; only the figure waits.
		expect(rows[0]).toMatchObject({ text: "Ended Wed Aug 26, 2026" });
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
	it("is the API's move on a week with a close, the oldest row shown included", () => {
		// AHM-81. Full time 40 h from Jan 5, ended Wed Feb 4, 8 h every
		// weekday through Fri Feb 6, read on Mar 5. The oldest row logged
		// 40 h against 24 expected, but the balance counts Mon–Wed only and
		// did not move: +16.0 from worked − expected would be wrong.
		const ended: Contract = {
			terms: [{ effectiveFrom: "2026-01-05", scheduleType: "full_time", fullTimeHours: 40 }],
			openingBalanceHours: 0,
			endedOn: "2026-02-04",
			companyHolidays: [],
			holidaysNotGiven: [],
		};
		const after = { worked: 0, contractExpected: 0, balanceEnd: 0, balanceMoved: 0 };
		const rows = ledgerRows(
			ledger(
				[
					week("2026-03-02", { ...after, balanceEnd: null, balanceMoved: null }),
					week("2026-02-23", after),
					week("2026-02-16", after),
					week("2026-02-09", after),
					week("2026-02-02", {
						worked: 40,
						contractExpected: 24,
						balanceEnd: 0,
						balanceMoved: 0,
					}),
				],
				{ totals: null, endedBalance: 0 },
			),
			{ kind: "day_job", contract: ended },
			"2026-03-05",
		);
		const oldest = rows[rows.length - 1];
		expect(oldest?.type === "week" && [oldest.week.weekOf, oldest.delta]).toEqual([
			"2026-02-02",
			0,
		]);
	});

	it("is worked − goal on a week with no close, and null without a goal", () => {
		const rows = ledgerRows(
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
		expect(rows.map((r) => (r.type === "week" ? r.delta : "-"))).toEqual([0.4, null]);
	});
});

function adjustment(
	date: string,
	kind: LedgerAdjustment["kind"],
	hours: number,
	applied: number,
	note?: string,
): LedgerAdjustment {
	return { id: `a-${date}`, date, kind, hours, applied, note };
}

describe("ledgerRows: adjustment rows", () => {
	it("puts an adjustment under the week it falls in, and one this week on top", () => {
		const rows = ledgerRows(
			ledger([
				week("2026-09-07", {
					adjustments: [adjustment("2026-09-08", "delta", -10, -10)],
				}),
				week("2026-08-31", {
					adjustments: [adjustment("2026-09-06", "cap", 20, -3)],
				}),
				week("2026-08-03", {
					adjustments: [adjustment("2026-08-04", "delta", 4, 4)],
				}),
				week("2026-07-27"),
			]),
			DAY_JOB,
			TODAY,
		);
		expect(shape(rows)).toEqual([
			"rule term 2027-01-04 planned",
			"adjustment 2026-09-08",
			"week 2026-08-31",
			"adjustment 2026-09-06",
			"week 2026-08-03",
			"adjustment 2026-08-04",
			"rule term 2026-08-03",
			"week 2026-07-27",
		]);
		expect(rows.filter((r) => r.type === "adjustment").map((r) => r.delta)).toEqual([-10, -3, 4]);
	});

	it("says what each kind did", () => {
		const rows = ledgerRows(
			ledger([
				week("2026-09-07"),
				week("2026-08-31", {
					adjustments: [
						adjustment("2026-08-31", "delta", -40, -40, "Paid out in August"),
						adjustment("2026-09-01", "reset", 0, -62.5),
						adjustment("2026-09-02", "cap", 50, -12.5),
						adjustment("2026-09-03", "cap", 50, 0),
					],
				}),
			]),
			DAY_JOB,
			TODAY,
		);
		const copy = rows.flatMap((r) => (r.type === "adjustment" ? [[r.text, r.sub]] : []));
		expect(copy).toEqual([
			["Thu Sep 3 · Capped at 50.0 h", "under the cap, nothing dropped"],
			["Wed Sep 2 · Capped at 50.0 h", "12.5 h over the cap dropped"],
			["Tue Sep 1 · Balance reset to 0.0 h", "was +62.5 h"],
			["Mon Aug 31 · Adjusted −40.0 h", "“Paid out in August”"],
		]);
	});

	it("names the balance the contract ended on, not what a settlement after it left", () => {
		const contract: Contract = {
			...CONTRACT,
			terms: CONTRACT.terms.slice(0, 2),
			endedOn: "2026-08-26",
		};
		const rows = ledgerRows(
			ledger(
				[
					week("2026-09-07"),
					week("2026-08-31", {
						contractExpected: 0,
						balanceEnd: 0,
						adjustments: [adjustment("2026-08-31", "delta", -5.7, -5.7)],
					}),
					week("2026-08-24", { contractExpected: 20.16, balanceEnd: 5.7 }),
				],
				{
					totals: { expected: 800, worked: 805.7, adjusted: -5.7, balance: 0 },
					endedBalance: 5.7,
				},
			),
			{ kind: "day_job", contract },
			TODAY,
		);
		expect(rows.find((r) => r.type === "rule" && r.rule === "ended")).toMatchObject({
			text: "Ended Wed Aug 26, 2026 · final balance +5.7 h",
		});
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
	it("writes an adjustment's hours in the delta column, so the column adds up", () => {
		const rows = ledgerRows(
			ledger([
				week("2026-09-07"),
				week("2026-08-31", {
					balanceEnd: -5,
					adjustments: [adjustment("2026-09-02", "delta", -10, -10, "August")],
				}),
				week("2026-08-24", { balanceEnd: 5 }),
			]),
			{ kind: "day_job", contract: { ...CONTRACT, terms: CONTRACT.terms.slice(0, 1) } },
			TODAY,
		);
		const lines = ledgerCsv(rows).trim().split("\n");
		expect(lines).toEqual([
			"week,expected,worked,delta,balance",
			"2026-08-31,33.6,33.6,0,-5",
			"Wed Sep 2 · Adjusted −10.0 h · “August”,,,-10,",
			"2026-08-24,33.6,33.6,0,5",
		]);
	});

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
