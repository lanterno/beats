import { describe, expect, it } from "vitest";
import {
	calculateDurationMinutes,
	formatDuration,
	formatSecondsToTime,
	parseTimedeltaToMinutes,
} from "./format";

describe("formatDuration", () => {
	it("returns minutes only when under an hour", () => {
		expect(formatDuration(45)).toBe("45.00m");
	});

	it("returns hours only when minutes are zero", () => {
		expect(formatDuration(120)).toBe("2h");
	});

	it("returns hours and minutes", () => {
		expect(formatDuration(150)).toBe("2h 30.00m");
	});

	it("handles zero", () => {
		expect(formatDuration(0)).toBe("0.00m");
	});

	it("handles falsy input (NaN treated as 0)", () => {
		expect(formatDuration(NaN)).toBe("0.00m");
	});

	it("handles fractional minutes", () => {
		expect(formatDuration(90.5)).toBe("1h 30.50m");
	});
});

describe("calculateDurationMinutes", () => {
	it("calculates minutes between two ISO strings", () => {
		const result = calculateDurationMinutes("2026-04-07T10:00:00Z", "2026-04-07T11:30:00Z");
		expect(result).toBe(90);
	});

	it("returns 0 when end is before start", () => {
		const result = calculateDurationMinutes("2026-04-07T12:00:00Z", "2026-04-07T10:00:00Z");
		expect(result).toBe(0);
	});

	it("handles strings without Z suffix", () => {
		const result = calculateDurationMinutes("2026-04-07T10:00:00", "2026-04-07T10:30:00");
		expect(result).toBe(30);
	});
});

describe("parseTimedeltaToMinutes", () => {
	it("parses H:MM:SS format", () => {
		expect(parseTimedeltaToMinutes("2:30:00")).toBe(150);
	});

	it("parses M:SS format", () => {
		expect(parseTimedeltaToMinutes("45:00")).toBe(45);
	});

	it("parses days with time", () => {
		expect(parseTimedeltaToMinutes("1 day, 2:00:00")).toBe(1560);
	});

	it("parses multiple days", () => {
		expect(parseTimedeltaToMinutes("3 days, 0:30:00")).toBe(4350);
	});

	it("returns 0 for empty string", () => {
		expect(parseTimedeltaToMinutes("")).toBe(0);
	});

	it("returns 0 for non-string input", () => {
		// @ts-expect-error testing invalid input
		expect(parseTimedeltaToMinutes(null)).toBe(0);
	});

	it("handles fractional seconds", () => {
		expect(parseTimedeltaToMinutes("0:01:30.5")).toBeCloseTo(1.508, 2);
	});
});

describe("formatSecondsToTime", () => {
	it("formats zero", () => {
		expect(formatSecondsToTime(0)).toBe("00:00:00");
	});

	it("formats hours, minutes, and seconds", () => {
		expect(formatSecondsToTime(3661)).toBe("01:01:01");
	});

	it("pads single-digit values", () => {
		expect(formatSecondsToTime(5)).toBe("00:00:05");
	});

	it("handles large values", () => {
		expect(formatSecondsToTime(86400)).toBe("24:00:00");
	});
});
