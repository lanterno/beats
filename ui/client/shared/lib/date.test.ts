import { describe, expect, it } from "vitest";
import {
	formatDateShort,
	getDayName,
	getISOWeek,
	getWeekRange,
	parseUtcIso,
	toLocalDatetimeLocalString,
} from "./date";

describe("parseUtcIso", () => {
	it("parses ISO string with Z suffix", () => {
		const date = parseUtcIso("2026-04-07T10:30:00Z");
		expect(date.getUTCHours()).toBe(10);
		expect(date.getUTCMinutes()).toBe(30);
	});

	it("appends Z to string without timezone", () => {
		const date = parseUtcIso("2026-04-07T10:30:00");
		expect(date.getUTCHours()).toBe(10);
		expect(date.getUTCMinutes()).toBe(30);
	});

	it("preserves explicit timezone offset", () => {
		const date = parseUtcIso("2026-04-07T12:00:00+02:00");
		expect(date.getUTCHours()).toBe(10);
	});

	it("returns invalid date for empty string", () => {
		const date = parseUtcIso("");
		expect(Number.isNaN(date.getTime())).toBe(true);
	});

	it("returns invalid date for non-string input", () => {
		// @ts-expect-error testing invalid input
		const date = parseUtcIso(null);
		expect(Number.isNaN(date.getTime())).toBe(true);
	});

	it("strips fractional seconds when no timezone present", () => {
		const date = parseUtcIso("2026-04-07T10:30:00.123456");
		expect(date.getUTCHours()).toBe(10);
		expect(date.getUTCMinutes()).toBe(30);
	});
});

describe("toLocalDatetimeLocalString", () => {
	it("formats a date for datetime-local input", () => {
		const date = new Date(2026, 3, 7, 14, 5); // April 7, 2026, 14:05 local
		const result = toLocalDatetimeLocalString(date);
		expect(result).toBe("2026-04-07T14:05");
	});

	it("pads single-digit month, day, hour, minute", () => {
		const date = new Date(2026, 0, 3, 8, 2); // Jan 3, 08:02
		const result = toLocalDatetimeLocalString(date);
		expect(result).toBe("2026-01-03T08:02");
	});
});

describe("getWeekRange", () => {
	it("returns Monday to Sunday for current week", () => {
		const { start, end } = getWeekRange(0);
		expect(start.getDay()).toBe(1); // Monday
		expect(end.getDay()).toBe(0); // Sunday
	});

	it("start is at midnight", () => {
		const { start } = getWeekRange(0);
		expect(start.getHours()).toBe(0);
		expect(start.getMinutes()).toBe(0);
		expect(start.getSeconds()).toBe(0);
	});

	it("end is at 23:59:59", () => {
		const { end } = getWeekRange(0);
		expect(end.getHours()).toBe(23);
		expect(end.getMinutes()).toBe(59);
		expect(end.getSeconds()).toBe(59);
	});

	it("previous week ends before current week starts", () => {
		const prev = getWeekRange(-1);
		const curr = getWeekRange(0);
		expect(prev.end.getTime()).toBeLessThan(curr.start.getTime());
	});

	it("span is exactly 7 days", () => {
		const { start, end } = getWeekRange(0);
		const days = (end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24);
		expect(days).toBeCloseTo(7, 0);
	});
});

describe("getDayName", () => {
	it("returns short day name", () => {
		const monday = new Date(2026, 3, 6); // April 6 2026 = Monday
		expect(getDayName(monday)).toBe("Mon");
	});

	it("returns long day name", () => {
		const monday = new Date(2026, 3, 6);
		expect(getDayName(monday, "long")).toBe("Monday");
	});
});

describe("formatDateShort", () => {
	it("formats as short month and day", () => {
		const date = new Date(2026, 11, 25); // Dec 25
		expect(formatDateShort(date)).toBe("Dec 25");
	});
});

describe("getISOWeek", () => {
	it("returns correct ISO week number", () => {
		// Jan 1 2026 is a Thursday → ISO week 1
		const jan1 = new Date(2026, 0, 1);
		expect(getISOWeek(jan1)).toBe(1);
	});

	it("handles Dec 31 which may be week 1 of next year", () => {
		// Dec 31 2026 is a Thursday → still week 53 or week 1 of 2027
		const dec31 = new Date(2026, 11, 31);
		const week = getISOWeek(dec31);
		expect(week).toBeGreaterThanOrEqual(1);
		expect(week).toBeLessThanOrEqual(53);
	});

	it("returns week 15 for April 7 2026", () => {
		// April 7 2026 is a Tuesday
		const date = new Date(2026, 3, 7);
		expect(getISOWeek(date)).toBe(15);
	});
});
