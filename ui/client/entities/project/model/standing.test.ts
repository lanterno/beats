import { describe, expect, it } from "vitest";
import {
	isFirstWeek,
	nominalLine,
	projection,
	weekLabel,
	weekRange,
	weekSentence,
} from "./standing";
import type { Contract, ContractDay, ContractTerm, ContractWeek } from "./types";

// The mockup's day job: 80% of 42 h, so 6.72 h a weekday; the week of
// Mon Sep 7, 2026 with Friday booked off, today Thursday, 1.88 h to go.
const TERM: ContractTerm = {
	effectiveFrom: "2026-08-03",
	scheduleType: "part_time",
	fullTimeHours: 42,
	percentage: 0.8,
};
const TODAY = "2026-09-10";
const PER_DAY = 6.72;

type DayPatch = Partial<ContractDay>;

function week(
	patches: Record<number, DayPatch> = {},
	extra: Partial<ContractWeek> = {},
): ContractWeek {
	const days: ContractDay[] = [0, 1, 2, 3, 4, 5, 6].map((i) => ({
		date: `2026-09-${String(7 + i).padStart(2, "0")}`,
		expected: i < 5 ? PER_DAY : 0,
		worked: 0,
		...patches[i],
	}));
	const expected = Math.round(days.reduce((s, d) => s + d.expected, 0) * 100) / 100;
	const worked = Math.round(days.reduce((s, d) => s + d.worked, 0) * 100) / 100;
	return {
		weekOf: "2026-09-07",
		expected,
		worked,
		remaining: Math.round((expected - worked) * 100) / 100,
		balance: 10.5,
		days,
		...extra,
	};
}

const VACATION: DayPatch = { expected: 0, absence: { type: "vacation", halfDay: false } };
const MOCKUP = week({
	0: { worked: 7.1 },
	1: { worked: 6.9 },
	2: { worked: 7.6 },
	3: { worked: 3.4 },
	4: VACATION,
});

describe("weekLabel", () => {
	it("says This week for today's week and the ISO week number for any other", () => {
		expect(weekLabel("2026-09-07", TODAY)).toBe("This week");
		expect(weekLabel("2026-08-31", TODAY)).toBe("Week 36");
		expect(weekRange("2026-08-31")).toBe("Aug 31 – Sep 6");
		expect(weekRange("2026-09-07")).toBe("Sep 7 – 13");
	});
});

describe("isFirstWeek", () => {
	const contract: Contract = {
		terms: [
			{ effectiveFrom: "2026-09-07", scheduleType: "full_time", fullTimeHours: 42, percentage: 1 },
		],
		openingBalanceHours: 0,
	};

	it("is the seven days from the first term's start, not the day before nor the eighth", () => {
		expect(isFirstWeek(contract, "2026-09-06")).toBe(false);
		expect(isFirstWeek(contract, "2026-09-07")).toBe(true);
		expect(isFirstWeek(contract, "2026-09-13")).toBe(true);
		expect(isFirstWeek(contract, "2026-09-14")).toBe(false);
	});
});

describe("projection", () => {
	it("charges today through Sunday for stop-now and adds what is to go for met", () => {
		// 10.5 − Thu 6.72 = 3.78; met adds the 1.88 still to go.
		expect(projection(MOCKUP, TODAY)).toEqual({ stopNow: 3.78, met: 5.66 });
	});

	it("does not add negative remaining: a week already over is met by stopping", () => {
		const over = week({ 0: { worked: 40 } });
		const p = projection(over, TODAY);
		expect(p?.met).toBe(p?.stopNow);
	});

	it("is null without a balance or an expectation, and when today is not in the week", () => {
		expect(projection(week({}, { balance: undefined }), TODAY)).toBeNull();
		expect(projection(week({}, { expected: undefined }), TODAY)).toBeNull();
		expect(projection(MOCKUP, "2026-09-14")).toBeNull();
	});

	it("rounds to two decimals as the API does, so float noise never reaches a sign", () => {
		// 6.74 − 6.72 in floating point is 0.020000000000000462.
		const p = projection(week({}, { balance: 6.74 }), "2026-09-11");
		expect(p?.stopNow).toBe(0.02);
	});
});

describe("nominalLine", () => {
	it("names each day off and what it took, only when the week expects less than the term", () => {
		expect(nominalLine(MOCKUP, TERM)).toBe("33.6 h nominal − Fri vacation 6.7 h");
		expect(nominalLine(week(), TERM)).toBeNull();
	});

	it("takes half for a half day and names a holiday", () => {
		const w = week({
			1: { expected: 3.36, absence: { type: "sick", halfDay: true } },
			4: { expected: 0, holiday: "Swiss National Day" },
		});
		expect(nominalLine(w, TERM)).toBe(
			"33.6 h nominal − Tue sick 3.4 h − Fri Swiss National Day 6.7 h",
		);
	});

	it("says nothing when the named days do not add up to the week's expectation", () => {
		// 60 % until Tuesday, 80 % from Wed Sep 9, Friday off: 5.04 + 5.04 + 6.72
		// + 6.72 = 23.52 expected. Neither term's nominal less Friday gives that.
		const change = week({ 0: { expected: 5.04 }, 1: { expected: 5.04 }, 4: VACATION });
		const sixty: ContractTerm = { ...TERM, effectiveFrom: "2026-01-05", percentage: 0.6 };
		expect(change.expected).toBe(23.52);
		expect(nominalLine(change, sixty)).toBeNull();
		expect(nominalLine(change, TERM)).toBeNull();
	});

	it("says nothing for a difference with no day to name", () => {
		// The term started on Wednesday: Mon and Tue expect nothing, and are not off.
		const w = week({ 0: { expected: 0 }, 1: { expected: 0 } });
		expect(nominalLine(w, TERM)).toBeNull();
	});
});

describe("weekSentence on a day job", () => {
	const say = (w: ContractWeek, todayIso = TODAY, nextWeek?: ContractWeek) =>
		weekSentence({ week: w, nextWeek, todayIso, kind: "day_job" });

	it("calls the week met when the remaining rounds to zero, done when it is over", () => {
		expect(say(week({}, { remaining: -0.04 }))).toBe("The week is met.");
		expect(say(week({}, { remaining: 0.04 }))).toBe("The week is met.");
		expect(say(week({}, { remaining: -0.4 }))).toBe("The week is done — 0.4 h over.");
	});

	it("puts it all on today when no later day expects hours, naming the days off and next Monday", () => {
		const next: ContractWeek = {
			weekOf: "2026-09-14",
			expected: 33.6,
			worked: 0,
			remaining: 33.6,
			days: [{ date: "2026-09-14", expected: PER_DAY, worked: 0 }],
		};
		expect(say(MOCKUP, TODAY, next)).toBe("1.9 h to go, all today. Friday is off, then Mon 6.7 h.");
		expect(say(MOCKUP)).toBe("1.9 h to go, all today. Friday is off.");
		expect(say(week({ 0: { worked: 31.7 } }), "2026-09-11")).toBe("1.9 h to go, all today.");
	});

	it("says nothing is due today and where the hours go", () => {
		const w = week({ 0: { worked: 20.16 }, 3: VACATION });
		expect(say(w)).toBe("Nothing due today (Vacation). 6.7 h to go on Friday.");
	});

	it("spreads the hours over the days that expect them", () => {
		const w = week({ 0: { worked: 21.2 } });
		expect(say(w)).toBe("12.4 h to go over Thu and Fri — about 6.2 h a day.");
		// Three in a row read as a range; a day off in the middle does not.
		expect(say(week({ 0: { worked: 13.44 } }), "2026-09-09")).toBe(
			"20.2 h to go over Wed – Fri — about 6.7 h a day.",
		);
		expect(say(week({ 0: { worked: 20.16 }, 3: VACATION }), "2026-09-09")).toBe(
			"6.7 h to go over Wed and Fri — about 3.4 h a day.",
		);
	});

	it("closes short when today and the rest of the week expect nothing", () => {
		expect(say(week({ 0: { worked: 31.7 } }), "2026-09-12")).toBe("The week closes 1.9 h short.");
	});

	it("falls back to the personal goal where the contract does not govern", () => {
		const objective = week({}, { expected: undefined, remaining: undefined, worked: 4.8 });
		expect(
			weekSentence({ week: objective, todayIso: TODAY, kind: "day_job", personalGoal: 8 }),
		).toBe("3.2 h to go over Thu – Sun — about 50 min a day.");
		expect(weekSentence({ week: objective, todayIso: TODAY, kind: "day_job" })).toBeNull();
	});

	it("is silent on a past week", () => {
		expect(say(MOCKUP, "2026-09-15")).toBeNull();
	});
});

describe("weekSentence on a side project", () => {
	const loom = { weekOf: "2026-09-07", worked: 4.8 };

	it("spreads the goal over the calendar days left, weekends included", () => {
		expect(
			weekSentence({ week: loom, todayIso: TODAY, kind: "side_project", personalGoal: 8 }),
		).toBe("3.2 h to go over Thu – Sun — about 50 min a day.");
		expect(
			weekSentence({ week: loom, todayIso: "2026-09-13", kind: "side_project", personalGoal: 8 }),
		).toBe("3.2 h to go, all today.");
		expect(
			weekSentence({ week: loom, todayIso: "2026-09-12", kind: "side_project", personalGoal: 8 }),
		).toBe("3.2 h to go over Sat and Sun — about 1.6 h a day.");
	});

	it("is met or done like a contract week", () => {
		expect(
			weekSentence({
				week: { ...loom, worked: 8.4 },
				todayIso: TODAY,
				kind: "side_project",
				personalGoal: 8,
			}),
		).toBe("The week is done — 0.4 h over.");
	});

	it("says nothing without a goal, under a cap, or with an expectation it must ignore", () => {
		expect(weekSentence({ week: loom, todayIso: TODAY, kind: "side_project" })).toBeNull();
		expect(
			weekSentence({ week: loom, todayIso: TODAY, kind: "side_project", personalGoal: null }),
		).toBeNull();
		expect(
			weekSentence({
				week: loom,
				todayIso: TODAY,
				kind: "freelance",
				personalGoal: 8,
				goalType: "cap",
			}),
		).toBeNull();
	});
});
