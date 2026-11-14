import { describe, expect, it } from "vitest";
import { KINDS } from "./lib/queue";
import { isStale, RUNBOOKS, runbook } from "./runbooks";

describe("isStale", () => {
	it("turns stale six calendar months after the review, not before", () => {
		expect(isStale("2026-05-14", new Date("2026-11-13T23:59:59Z"))).toBe(false);
		expect(isStale("2026-05-14", new Date("2026-11-14T00:00:00Z"))).toBe(true);
	});

	it("treats a date it cannot read as stale", () => {
		expect(isStale("soon", new Date("2026-11-14T00:00:00Z"))).toBe(true);
	});
});

describe("the runbooks", () => {
	// A queue row whose "Read the runbook" link went nowhere would fail in
	// the moment it was needed.
	it("has one for every kind of queue row", () => {
		for (const kind of Object.values(KINDS)) {
			expect(runbook(kind.runbook), kind.runbook).toBeDefined();
		}
	});

	it("has no two with the same id", () => {
		expect(new Set(RUNBOOKS.map((r) => r.id)).size).toBe(RUNBOOKS.length);
	});
});
