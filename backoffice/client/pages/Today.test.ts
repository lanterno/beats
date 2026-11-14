import { describe, expect, it } from "vitest";
import { monthSpend, todayHeadline } from "./Today";

const NOW = new Date("2026-11-14T12:00:00Z");
const row = (due: string) => ({
	kind: "job_failed" as const,
	subject_id: "x",
	since: due,
	due,
	count: 1,
});

describe("todayHeadline", () => {
	it("says nothing needs you on an empty queue", () => {
		expect(todayHeadline([], NOW)).toBe("Nothing needs you right now.");
	});

	it("leads with what is overdue", () => {
		expect(todayHeadline([row("2026-11-13T00:00:00Z"), row("2026-11-20T00:00:00Z")], NOW)).toBe(
			"One thing is overdue.",
		);
	});

	it("counts what needs you when nothing is overdue", () => {
		expect(todayHeadline([row("2026-11-20T00:00:00Z"), row("2026-11-21T00:00:00Z")], NOW)).toBe(
			"2 things need you.",
		);
	});
});

describe("monthSpend", () => {
	const cost = (day: string, cost_usd: number) => ({
		day,
		model: "m",
		cost_usd,
		input_tokens: 0,
		cache_read_tokens: 0,
		calls: 1,
	});

	it("sums this UTC month only", () => {
		const capacity = {
			collections: [],
			coach_cost: [cost("2026-10-31", 9), cost("2026-11-01", 1.5), cost("2026-11-14", 2)],
		};
		expect(monthSpend(capacity, NOW)).toBe(3.5);
	});
});
