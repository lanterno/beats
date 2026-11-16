import { describe, expect, it } from "vitest";
import type { AccountRow } from "@/shared/api/schema";
import {
	bucketDays,
	everyBucket,
	hoursHeadline,
	hoursOf,
	hoursSentence,
	peopleHeadline,
	SPANS,
	sortRows,
} from "./usage";

describe("bucketDays", () => {
	it("walks days, Mondays and firsts from the API's first bucket", () => {
		expect(bucketDays("2026-11-14", "day", 3)).toEqual(["2026-11-14", "2026-11-15", "2026-11-16"]);
		expect(bucketDays("2026-12-28", "week", 2)).toEqual(["2026-12-28", "2027-01-04"]);
		expect(bucketDays("2025-11-01", "month", 3)).toEqual([
			"2025-11-01",
			"2025-12-01",
			"2026-01-01",
		]);
	});
});

describe("everyBucket", () => {
	it("fills the quiet buckets with nothing and keeps the API's figures", () => {
		const drawn = everyBucket(
			[{ period: "2026-11-16", hours: 2.5, sessions: 3, accounts: 2 }],
			"2026-11-14",
			"day",
			3,
		);
		expect(drawn).toEqual([
			{ day: "2026-11-14", value: 0, sessions: 0, accounts: 0 },
			{ day: "2026-11-15", value: 0, sessions: 0, accounts: 0 },
			{ day: "2026-11-16", value: 2.5, sessions: 3, accounts: 2 },
		]);
	});
});

describe("hoursOf", () => {
	it("reads with a thousands separator and no trailing decimals", () => {
		expect(hoursOf(0)).toBe("0 h");
		expect(hoursOf(0.25)).toBe("0.25 h");
		expect(hoursOf(1234.5)).toBe("1,234.5 h");
		expect(hoursOf(2.004)).toBe("2 h");
	});
});

describe("the sentences", () => {
	it("say what was logged and when the most was, per unit", () => {
		const drawn = everyBucket(
			[
				{ period: "2026-11-02", hours: 4, sessions: 1, accounts: 1 },
				{ period: "2026-11-09", hours: 6, sessions: 2, accounts: 1 },
			],
			"2026-11-02",
			"week",
			2,
		);
		expect(hoursSentence(drawn, "week")).toBe(
			"10 h logged over the last 2 weeks. The busiest week was in the one starting 2026-11-09, with 6 h.",
		);
		expect(hoursSentence(everyBucket([], "2026-11-16", "day", 1), "day")).toBe(
			"Nothing was logged in the last 1 day.",
		);
	});

	it("open on the totals", () => {
		expect(hoursHeadline(0, 0)).toBe("No hours have been logged yet.");
		expect(hoursHeadline(12.5, 1)).toBe("12.5 h logged all told, by 1 person in the last 30 days.");
		expect(hoursHeadline(12.5, 0)).toBe("12.5 h logged all told, by nobody in the last 30 days.");
		expect(peopleHeadline(0, 0)).toBe("Nobody has an account yet.");
		expect(peopleHeadline(1, 1)).toBe(
			"1 person has an account, and 1 was here in the last 30 days.",
		);
		expect(peopleHeadline(40, 12)).toBe(
			"40 people have an account, and 12 were here in the last 30 days.",
		);
	});
});

describe("SPANS", () => {
	it("opens on the shortest span of each unit", () => {
		for (const spans of Object.values(SPANS)) {
			expect(spans[0]).toBe(Math.min(...spans));
		}
	});
});

const row = (id: string, over: Partial<AccountRow>): AccountRow => ({
	id,
	email: `${id}@example.test`,
	created_at: null,
	last_seen_on: null,
	suspended: false,
	projects: 0,
	sessions: 0,
	...over,
});

describe("sortRows", () => {
	const rows = [
		row("a", { created_at: "2026-11-10T00:00:00+00:00", last_seen_on: null, projects: 1 }),
		row("b", { created_at: "2026-11-01T00:00:00+00:00", last_seen_on: "2026-11-15", projects: 3 }),
		row("c", { created_at: null, last_seen_on: "2026-11-12", projects: 3, sessions: 9 }),
	];
	it("puts the largest or newest first, never seen and never created last", () => {
		expect(sortRows(rows, "created").map((r) => r.id)).toEqual(["a", "b", "c"]);
		expect(sortRows(rows, "seen").map((r) => r.id)).toEqual(["b", "c", "a"]);
		expect(sortRows(rows, "sessions").map((r) => r.id)).toEqual(["c", "a", "b"]);
	});
	it("keeps the API's order on a tie", () => {
		expect(sortRows(rows, "projects").map((r) => r.id)).toEqual(["b", "c", "a"]);
	});
});
