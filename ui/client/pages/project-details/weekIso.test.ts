/**
 * The week columns on the project page are keyed by these strings, so an
 * off-by-one lands a week's hours under the wrong heading. Extracted from
 * ProjectDetails, where they were unexported and therefore untestable.
 */
import { describe, expect, it } from "vitest";
import { computeMondayIsoList, getMondayIsoFor } from "./weekIso";

describe("getMondayIsoFor", () => {
	it("returns the same day when today is already Monday", () => {
		// 2026-04-27 is a Monday.
		expect(getMondayIsoFor(0, new Date(2026, 3, 27, 9))).toBe("2026-04-27");
	});

	it("walks back to Monday from any weekday", () => {
		for (let offset = 0; offset < 7; offset++) {
			const day = new Date(2026, 3, 27 + offset, 9);
			expect(getMondayIsoFor(0, day)).toBe("2026-04-27");
		}
	});

	it("counts back whole weeks", () => {
		const wednesday = new Date(2026, 3, 29, 9);
		expect(getMondayIsoFor(1, wednesday)).toBe("2026-04-20");
		expect(getMondayIsoFor(4, wednesday)).toBe("2026-03-30");
	});

	it("crosses a month and a year boundary", () => {
		expect(getMondayIsoFor(1, new Date(2026, 0, 5, 9))).toBe("2025-12-29");
	});

	it("zero-pads month and day", () => {
		expect(getMondayIsoFor(0, new Date(2026, 0, 5, 9))).toBe("2026-01-05");
	});

	it("holds across a spring-forward boundary", () => {
		// Europe/London springs forward on 2026-03-29. A midnight anchor can
		// slip a day here; noon cannot.
		const afterDst = new Date(2026, 2, 30, 9);
		expect(getMondayIsoFor(0, afterDst)).toBe("2026-03-30");
		expect(getMondayIsoFor(1, afterDst)).toBe("2026-03-23");
	});
});

describe("computeMondayIsoList", () => {
	it("returns the requested number of Mondays, most recent first", () => {
		const list = computeMondayIsoList(3, new Date(2026, 3, 29, 9));
		expect(list).toEqual(["2026-04-27", "2026-04-20", "2026-04-13"]);
	});

	it("is empty for a zero count", () => {
		expect(computeMondayIsoList(0, new Date(2026, 3, 29, 9))).toEqual([]);
	});
});
