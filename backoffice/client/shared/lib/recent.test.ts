import { describe, expect, it } from "vitest";
import { fresh, type Opened, RECENT_LIMIT, withOpened } from "./recent";

const TODAY = new Date("2026-11-09T14:00:00Z");
const on = (day: string, id = "a"): Opened => ({ id, day });

describe("fresh", () => {
	it("keeps an entry from today and one from six days ago", () => {
		const kept = [on("2026-11-09"), on("2026-11-03", "b")];
		expect(fresh(kept, TODAY)).toEqual(kept);
	});

	// The boundary is the whole point: the panel promises a week.
	it("drops the entry that turns seven days old", () => {
		expect(fresh([on("2026-11-03")], TODAY)).toHaveLength(1);
		expect(fresh([on("2026-11-02")], TODAY)).toHaveLength(0);
	});

	it("drops an entry dated in the future, which is a clock that moved", () => {
		expect(fresh([on("2026-11-10")], TODAY)).toEqual([]);
	});

	it("drops anything malformed rather than failing", () => {
		const mixed = [on("2026-11-09"), { id: "x" }, { day: "2026-11-09" }, null, "nope", 7];
		expect(fresh(mixed, TODAY)).toEqual([on("2026-11-09")]);
		expect(fresh("not a list", TODAY)).toEqual([]);
		expect(fresh(undefined, TODAY)).toEqual([]);
	});

	it("rejects a day that is not a day", () => {
		expect(fresh([{ id: "a", day: "yesterday" }], TODAY)).toEqual([]);
	});

	// The month and year boundaries are where naive date arithmetic breaks.
	it("counts across a month and a year boundary", () => {
		expect(fresh([on("2026-10-30")], new Date("2026-11-02T00:00:00Z"))).toHaveLength(1);
		expect(fresh([on("2025-12-30")], new Date("2026-01-02T00:00:00Z"))).toHaveLength(1);
		expect(fresh([on("2025-12-24")], new Date("2026-01-02T00:00:00Z"))).toHaveLength(0);
	});
});

describe("withOpened", () => {
	it("puts the newest first", () => {
		expect(withOpened([on("2026-11-01", "b")], "a", TODAY)).toEqual([
			{ id: "a", day: "2026-11-09" },
			{ id: "b", day: "2026-11-01" },
		]);
	});

	// Opening the same account twice is the common case, and two rows for it
	// would push everything else out.
	it("moves an account already there rather than repeating it", () => {
		const before = [on("2026-11-01", "a"), on("2026-11-01", "b")];
		expect(withOpened(before, "b", TODAY)).toEqual([
			{ id: "b", day: "2026-11-09" },
			{ id: "a", day: "2026-11-01" },
		]);
	});

	it("keeps the list short", () => {
		let list: Opened[] = [];
		for (let i = 0; i < RECENT_LIMIT + 4; i++) list = withOpened(list, `id-${i}`, TODAY);
		expect(list).toHaveLength(RECENT_LIMIT);
		expect(list[0].id).toBe(`id-${RECENT_LIMIT + 3}`);
	});

	// The one rule this file exists to keep: an address must not reach a URL,
	// browser history, or this list (docs/backoffice.md § The line).
	it("stores the id it was given and nothing beside it", () => {
		const [entry] = withOpened([], "6730f1a2b3c4d5e6f7a8b9c0", TODAY);
		expect(Object.keys(entry).sort()).toEqual(["day", "id"]);
	});
});
