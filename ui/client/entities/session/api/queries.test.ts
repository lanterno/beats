import { describe, expect, it } from "vitest";
import { computeWeekRanges } from "./queries";

describe("computeWeekRanges", () => {
	it("returns the requested number of consecutive weeks", () => {
		const now = new Date(2026, 4, 1, 12, 0, 0); // Friday
		const ranges = computeWeekRanges(4, now);
		expect(ranges.length).toBe(4);
	});

	it("ends at the current ISO week (Monday-anchored)", () => {
		// 2026-05-01 is Friday. ISO week starts Monday 2026-04-27.
		const now = new Date(2026, 4, 1, 12, 0, 0);
		const ranges = computeWeekRanges(1, now);
		expect(ranges[0].weekStartKey).toBe("2026-04-27");
	});

	it("orders ranges oldest-first so a chart reads left-to-right", () => {
		const now = new Date(2026, 4, 1, 12, 0, 0);
		const ranges = computeWeekRanges(3, now);
		// Each range's weekStartKey should be ascending.
		const keys = ranges.map((r) => r.weekStartKey);
		const sorted = [...keys].sort();
		expect(keys).toEqual(sorted);
	});

	it("each range spans exactly 7 days", () => {
		const now = new Date(2026, 4, 1, 12, 0, 0);
		const ranges = computeWeekRanges(2, now);
		for (const r of ranges) {
			const diff = new Date(r.end).getTime() - new Date(r.start).getTime();
			expect(Math.round(diff / (1000 * 60 * 60 * 24))).toBe(7);
		}
	});

	it("treats Sunday as the *end* of the previous ISO week, not the start", () => {
		// 2026-05-03 is a Sunday. The current ISO week should still be
		// the one that started Monday 2026-04-27 — Sunday closes it.
		const now = new Date(2026, 4, 3, 12, 0, 0);
		const ranges = computeWeekRanges(1, now);
		expect(ranges[0].weekStartKey).toBe("2026-04-27");
	});
});
