import { describe, expect, it } from "vitest";
import { changes } from "./changes";

describe("changes", () => {
	it("names each field whose value differs, in key order", () => {
		expect(
			changes(
				{ suspended: false, suspended_kind: null, sessions_valid_after: null },
				{ suspended: true, suspended_kind: "abuse", sessions_valid_after: null },
			),
		).toEqual(["suspended: false → true", "suspended_kind: — → abuse"]);
	});

	it("reads a field one side lacks as nothing on that side", () => {
		expect(
			changes({ overridden: false }, { overridden: true, writes_per_minute_beats: 5 }),
		).toEqual(["overridden: false → true", "writes_per_minute_beats: — → 5"]);
		expect(changes({ overridden: true, set_by: "op" }, { overridden: false })).toEqual([
			"overridden: true → false",
			"set_by: op → —",
		]);
	});

	it("treats a missing field and a null one as the same nothing", () => {
		expect(changes({ closes_on: null }, {})).toEqual([]);
	});

	it("says nothing when nothing moved, and copes with either side absent", () => {
		expect(
			changes({ owners: 0, closes_on: "2026-12-31" }, { owners: 0, closes_on: "2026-12-31" }),
		).toEqual([]);
		expect(changes(null, undefined)).toEqual([]);
	});

	it("writes a nested value out whole", () => {
		expect(changes({ limits: { beats: 5 } }, { limits: { beats: 9 } })).toEqual([
			'limits: {"beats":5} → {"beats":9}',
		]);
	});
});
