import { describe, expect, it } from "vitest";
import { cacheSentence, coachMonth, dailyCost, sparkPoints } from "./capacity";

const cost = (day: string, model: string, cost_usd: number, input = 0, cached = 0) => ({
	day,
	model,
	cost_usd,
	input_tokens: input,
	cache_read_tokens: cached,
	calls: 1,
});

const NOON_14TH = new Date("2026-11-14T12:00:00Z");

describe("dailyCost", () => {
	it("adds the models up a day and fills the quiet days with nothing", () => {
		const days = dailyCost(
			[cost("2026-11-14", "a", 1), cost("2026-11-14", "b", 0.5), cost("2026-11-12", "a", 2)],
			3,
			NOON_14TH,
		);
		expect(days).toEqual([
			{ day: "2026-11-12", value: 2 },
			{ day: "2026-11-13", value: 0 },
			{ day: "2026-11-14", value: 1.5 },
		]);
	});
});

describe("coachMonth", () => {
	it("counts this UTC month only, and carries its pace to the month's end", () => {
		const month = coachMonth(
			[cost("2026-10-31", "a", 100), cost("2026-11-01", "a", 3), cost("2026-11-13", "a", 3.5)],
			NOON_14TH,
		);
		expect(month.spent).toBe(6.5);
		expect(month.running).toHaveLength(14);
		expect(month.running[0]).toBe(3);
		expect(month.running[month.running.length - 1]).toBe(6.5);
		// 13.5 of November's 30 days have gone.
		expect(month.heading).toBeCloseTo((6.5 * 30) / 13.5, 6);
	});

	it("says nothing about the month's heading before a whole day has gone", () => {
		const month = coachMonth([cost("2026-11-01", "a", 3)], new Date("2026-11-01T20:00:00Z"));
		expect(month.spent).toBe(3);
		expect(month.heading).toBeNull();
	});
});

describe("cacheSentence", () => {
	it("says the cache's share of all the input and the model most of the bill went to", () => {
		const rows = [
			cost("2026-11-14", "big", 9, 100, 300),
			cost("2026-11-13", "small", 1, 0, 0),
			// Outside the 7 days shown.
			cost("2026-11-01", "small", 500, 1000, 0),
		];
		expect(cacheSentence(rows, 7, NOON_14TH)).toBe(
			"75% of the input came from the cache. big is 90% of the bill.",
		);
	});

	it("says when one model had it all, and when nothing was spent", () => {
		expect(cacheSentence([cost("2026-11-14", "big", 2, 10, 0)], 7, NOON_14TH)).toBe(
			"0% of the input came from the cache. It all went to big.",
		);
		expect(cacheSentence([], 30, NOON_14TH)).toBe(
			"The coach hasn't cost anything in these 30 days.",
		);
	});
});

describe("sparkPoints", () => {
	it("spans the box with the lowest value at the bottom and the highest at the top", () => {
		expect(sparkPoints([0, 5, 10], 84, 24)).toBe("1.0,23.0 42.0,12.0 83.0,1.0");
		expect(sparkPoints([], 84, 24)).toBe("");
	});
});
