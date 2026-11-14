import { describe, expect, it } from "vitest";
import { bucketOf, dueLabel, queueHeadline } from "./queue";

const NOW = new Date("2026-11-14T12:00:00Z");
const at = (iso: string) => ({ since: "2026-11-01T00:00:00Z", due: iso });

describe("bucketOf", () => {
	it("is overdue the moment the due instant has passed", () => {
		expect(bucketOf(at("2026-11-14T11:59:59Z"), NOW)).toBe("overdue");
		expect(bucketOf(at("2026-11-14T12:00:00Z"), NOW)).toBe("today");
	});

	it("is today up to the next UTC midnight, later from it", () => {
		expect(bucketOf(at("2026-11-14T23:59:59Z"), NOW)).toBe("today");
		expect(bucketOf(at("2026-11-15T00:00:00Z"), NOW)).toBe("later");
	});

	// Nothing says how long an ownerless organisation has been ownerless.
	it("puts a row with no stored date in today, never overdue", () => {
		expect(bucketOf({ since: null, due: "2026-11-14T11:00:00Z" }, NOW)).toBe("today");
	});
});

describe("dueLabel", () => {
	it("counts overdue days, and hours under a day", () => {
		expect(dueLabel(at("2026-11-11T12:00:00Z"), NOW)).toBe("Overdue 3 d");
		expect(dueLabel(at("2026-11-14T10:00:00Z"), NOW)).toBe("Overdue 2 h");
		expect(dueLabel(at("2026-11-14T11:59:30Z"), NOW)).toBe("Overdue 1 h");
	});

	it("counts days left, rounding up", () => {
		expect(dueLabel(at("2026-11-15T06:00:00Z"), NOW)).toBe("1 day left");
		expect(dueLabel(at("2026-11-19T13:00:00Z"), NOW)).toBe("6 days left");
	});
});

describe("queueHeadline", () => {
	const row = (due: string) => ({
		kind: "job_failed" as const,
		subject_id: "x",
		since: due,
		due,
		count: 1,
	});

	it("says nothing is waiting on an empty queue", () => {
		expect(queueHeadline([], NOW)).toBe("Nothing is waiting.");
	});

	it("names how many are overdue", () => {
		expect(queueHeadline([row("2026-11-13T00:00:00Z"), row("2026-11-20T00:00:00Z")], NOW)).toBe(
			"Two things are waiting. One is overdue.",
		);
	});

	it("falls back to figures past the words it has", () => {
		const many = Array.from({ length: 5 }, () => row("2026-11-20T00:00:00Z"));
		expect(queueHeadline(many, NOW)).toBe("5 things are waiting.");
	});
});
