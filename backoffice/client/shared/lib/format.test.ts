import { describe, expect, it } from "vitest";
import { dayOf, everyDay, formatBytes, minuteOf } from "./format";

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

describe("minuteOf", () => {
	it("reads the minute off an instant, however its zone is written", () => {
		expect(minuteOf("2026-11-08T19:31:59.390039+00:00")).toBe("2026-11-08 19:31");
		expect(minuteOf("2026-11-08T19:31:59Z")).toBe("2026-11-08 19:31");
	});

	it("dashes what isn't an instant", () => {
		expect(minuteOf(null)).toBe("—");
		expect(minuteOf(undefined)).toBe("—");
		expect(minuteOf(1731094319)).toBe("—");
	});
});

describe("everyDay", () => {
	const today = new Date("2026-03-02T23:59:00Z");

	it("counts the days the API left out as nothing, oldest first", () => {
		expect(everyDay([{ day: "2026-03-01", value: 4 }], 3, today)).toEqual([
			{ day: "2026-02-28", value: 0 },
			{ day: "2026-03-01", value: 4 },
			{ day: "2026-03-02", value: 0 },
		]);
	});

	it("drops a day older than the window", () => {
		const days = everyDay([{ day: "2026-02-27", value: 9 }], 3, today);
		expect(days.map((d) => d.value)).toEqual([0, 0, 0]);
	});

	it("matches a row by its day when the API sends an instant", () => {
		const days = everyDay([{ day: "2026-03-02T00:00:00+00:00", value: 2 }], 1, today);
		expect(days).toEqual([{ day: "2026-03-02", value: 2 }]);
	});
});
