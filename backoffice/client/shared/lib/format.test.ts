import { describe, expect, it } from "vitest";
import { dayOf, formatBytes } from "./format";

describe("formatBytes", () => {
	it("walks the units with one decimal until three digits", () => {
		expect(formatBytes(0)).toBe("0 B");
		expect(formatBytes(999)).toBe("999 B");
		expect(formatBytes(1536)).toBe("1.5 KB");
		expect(formatBytes(10 * 1024 ** 3)).toBe("10 GB");
		expect(formatBytes(150 * 1024)).toBe("150 KB");
	});

	it("refuses nonsense rather than rendering it", () => {
		expect(formatBytes(-1)).toBe("—");
		expect(formatBytes(Number.NaN)).toBe("—");
	});
});

describe("dayOf", () => {
	it("reads the day off an instant or a date, and dashes nothing", () => {
		expect(dayOf("2026-11-04T12:30:00+00:00")).toBe("2026-11-04");
		expect(dayOf("2026-11-04")).toBe("2026-11-04");
		expect(dayOf(null)).toBe("—");
		expect(dayOf(undefined)).toBe("—");
	});
});
