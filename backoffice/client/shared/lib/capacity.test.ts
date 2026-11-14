import { describe, expect, it } from "vitest";
import type { CapacityReport } from "@/shared/api/schema";
import {
	cacheSentence,
	coachMonth,
	dailyCost,
	dailyCostByFamily,
	familyOf,
	growthCell,
	MODEL_FAMILIES,
	moved,
	sizeChart,
	sizeHeadline,
	sparkPoints,
} from "./capacity";

const cost = (day: string, model: string, cost_usd: number, input = 0, cached = 0, saved = 0) => ({
	day,
	model,
	cost_usd,
	input_tokens: input,
	cache_read_tokens: cached,
	calls: 1,
	cache_saved_usd: saved,
});

const NOON_14TH = new Date("2026-11-14T12:00:00Z");

describe("dailyCost", () => {
	it("adds the models up a day and fills the quiet days with nothing", () => {
		const days = dailyCost(
			[cost("2026-11-14", "a", 1), cost("2026-11-14", "b", 0.5), cost("2026-11-12", "a", 2)],
			3,
			NOON_14TH,
		);
		expect(days).toEqual([
			{ day: "2026-11-12", value: 2 },
			{ day: "2026-11-13", value: 0 },
			{ day: "2026-11-14", value: 1.5 },
		]);
	});
});

describe("coachMonth", () => {
	it("counts this UTC month only, and carries its pace to the month's end", () => {
		const month = coachMonth(
			[cost("2026-10-31", "a", 100), cost("2026-11-01", "a", 3), cost("2026-11-13", "a", 3.5)],
			NOON_14TH,
		);
		expect(month.spent).toBe(6.5);
		expect(month.running).toHaveLength(14);
		expect(month.running[0]).toBe(3);
		expect(month.running[month.running.length - 1]).toBe(6.5);
		// 13.5 of November's 30 days have gone.
		expect(month.heading).toBeCloseTo((6.5 * 30) / 13.5, 6);
	});

	it("says nothing about the month's heading before a whole day has gone", () => {
		const month = coachMonth([cost("2026-11-01", "a", 3)], new Date("2026-11-01T20:00:00Z"));
		expect(month.spent).toBe(3);
		expect(month.heading).toBeNull();
	});
});

describe("cacheSentence", () => {
	it("says the cache's share of all the input and the model most of the bill went to", () => {
		const rows = [
			cost("2026-11-14", "big", 9, 100, 300, 2.5),
			cost("2026-11-13", "small", 1, 0, 0),
			// Outside the 7 days shown.
			cost("2026-11-01", "small", 500, 1000, 0, 80),
		];
		expect(cacheSentence(rows, 7, NOON_14TH)).toBe(
			"75% of the input came from the cache, which saved about $2.50. big is 90% of the bill.",
		);
	});

	it("says when one model had it all, and when nothing was spent", () => {
		expect(cacheSentence([cost("2026-11-14", "big", 2, 10, 0)], 7, NOON_14TH)).toBe(
			"0% of the input came from the cache. It all went to big.",
		);
		expect(cacheSentence([], 30, NOON_14TH)).toBe(
			"The coach hasn't cost anything in these 30 days.",
		);
	});
});

describe("cacheSentence's saving", () => {
	it("says when writing the cache cost more than reading it saved", () => {
		expect(cacheSentence([cost("2026-11-14", "big", 2, 10, 10, -0.4)], 7, NOON_14TH)).toBe(
			"50% of the input came from the cache, and writing it cost $0.40 more than reading it saved. It all went to big.",
		);
	});

	it("does not round a few cents' saving up to a claim", () => {
		expect(cacheSentence([cost("2026-11-14", "big", 2, 10, 10, 0.004)], 7, NOON_14TH)).toBe(
			"50% of the input came from the cache, which saved next to nothing. It all went to big.",
		);
	});
});

describe("sparkPoints", () => {
	it("spans the box with the lowest value at the bottom and the highest at the top", () => {
		expect(sparkPoints([0, 5, 10], 84, 24)).toBe("1.0,23.0 42.0,12.0 83.0,1.0");
		expect(sparkPoints([], 84, 24)).toBe("");
	});
});

const MB = 1024 * 1024;
const size = (day: string, mb: number) => ({ day, storage_bytes: Math.round(mb * MB) });
const collection = (
	name: string,
	mb: number,
	growth: { bytes?: number | null; share?: number | null } = {},
): CapacityReport["collections"][number] => ({
	name,
	documents: 1,
	storage_bytes: Math.round(mb * MB),
	index_bytes: 0,
	growth_bytes_a_month: growth.bytes ?? null,
	growth_share_a_month: growth.share ?? null,
});
const growth = (since: string, until: string, change: number, perMonth: number) => ({
	since,
	until,
	change_bytes: change,
	bytes_a_month: perMonth,
});

describe("sizeHeadline", () => {
	it("before any size is kept, says where the database stands and when the pace will show", () => {
		const said = sizeHeadline(
			{ sizes: [], growth: null, collections: [collection("beats", 3), collection("flow", 1)] },
			NOON_14TH,
		);
		expect(said.title).toBe("The database takes up 4 MB.");
		expect(said.lead).toBe(
			"beats is the largest of 2 collections, at 3 MB. The job runner keeps the database's size once a day from its next run; the pace shows the day after, once there are two to compare.",
		);
	});

	it("with one size kept, names the day the pace will show", () => {
		const said = sizeHeadline(
			{ sizes: [size("2026-11-30", 4)], growth: null, collections: [collection("beats", 4)] },
			NOON_14TH,
		);
		expect(said.lead).toContain("Sizes are kept once a day from 30 November;");
		expect(said.lead).toContain("the pace shows from 1 December");
	});

	it("says the pace, and the collection that adds the most to it", () => {
		const said = sizeHeadline(
			{
				sizes: [size("2026-10-15", 3), size("2026-11-14", 3.2)],
				growth: growth("2026-10-15", "2026-11-14", 0.2 * MB, 0.2 * MB),
				collections: [
					collection("beats", 2, { bytes: 0.05 * MB, share: 0.02 }),
					// The fastest share is not the most bytes.
					collection("tiny", 0.01, { bytes: 0.01 * MB, share: 2 }),
					collection("flow", 1.2, { bytes: 0.14 * MB, share: 0.12 }),
				],
			},
			NOON_14TH,
		);
		expect(said.title).toBe("The database grows about 205 KB a month.");
		expect(said.lead).toBe(
			"flow grows fastest, about 143 KB a month. Measured from 15 October to 14 November.",
		);
	});

	it("says a database that shrank, or held its size, in those words", () => {
		const base = { sizes: [], collections: [collection("beats", 2, { bytes: -MB, share: -0.3 })] };
		expect(
			sizeHeadline({ ...base, growth: growth("2026-10-15", "2026-11-14", -MB, -MB) }, NOON_14TH),
		).toEqual({
			title: "The database shrinks about 1 MB a month.",
			lead: "No collection grew. Measured from 15 October to 14 November.",
		});
		expect(
			sizeHeadline({ ...base, growth: growth("2026-10-15", "2026-11-14", 0, 0) }, NOON_14TH).title,
		).toBe("The database has kept its size since 15 October.");
	});

	it("says a pace read over a few days will settle, and a runner that stopped", () => {
		const fresh = sizeHeadline(
			{ sizes: [], growth: growth("2026-11-13", "2026-11-14", MB, 30 * MB), collections: [] },
			NOON_14TH,
		);
		expect(fresh.lead).toBe(
			"No collection grew. Measured over the one day kept so far, so it will settle as more are kept.",
		);
		const stopped = sizeHeadline(
			{ sizes: [], growth: growth("2026-10-10", "2026-11-09", MB, MB), collections: [] },
			NOON_14TH,
		);
		expect(stopped.lead).toContain("The job runner last kept a size on 9 November.");
		// Yesterday's size is not stale: today's is kept on the next tick.
		const yesterday = sizeHeadline(
			{ sizes: [], growth: growth("2026-10-14", "2026-11-13", MB, MB), collections: [] },
			NOON_14TH,
		);
		expect(yesterday.lead).not.toContain("last kept");
	});
});

describe("moved", () => {
	it("says what the database moved since the pace's first day", () => {
		expect(moved(growth("2026-10-15", "2026-11-14", 2 * MB, 2 * MB))).toBe(
			"Up 2 MB since 15 October.",
		);
		expect(moved(growth("2026-10-15", "2026-11-14", -MB, -MB))).toBe("Down 1 MB since 15 October.");
		expect(moved(growth("2026-10-15", "2026-11-14", 0, 0))).toBe("No change since 15 October.");
	});
});

describe("growthCell", () => {
	it("says a share a month, signed, with a real minus", () => {
		expect(growthCell(collection("a", 1, { bytes: 1, share: 0.054 }), true)).toBe("+5%");
		expect(growthCell(collection("a", 1, { bytes: -1, share: -0.03 }), true)).toBe("−3%");
		expect(growthCell(collection("a", 1, { bytes: 1, share: 0.001 }), true)).toBe("0%");
	});

	it("says bytes when there was nothing to take a share of, and New for a collection made since", () => {
		expect(growthCell(collection("a", 1, { bytes: 2 * MB, share: null }), true)).toBe("+2 MB");
		expect(growthCell(collection("a", 1), true)).toBe("New");
	});

	it("says nothing before there is a pace", () => {
		expect(growthCell(collection("a", 1), false)).toBe("—");
	});
});

describe("sizeChart", () => {
	const points = (line: string) =>
		line.split(" ").map((p) => p.split(",").map(Number) as [number, number]);

	it("draws nothing from fewer than two sizes", () => {
		expect(sizeChart([], null, 760, 150)).toBeNull();
		expect(sizeChart([size("2026-11-14", 3)], null, 760, 150)).toBeNull();
	});

	it("carries the pace on from the newest size, as far as the history goes back", () => {
		const sizes = [size("2026-08-16", 2), size("2026-11-14", 3)];
		const chart = sizeChart(sizes, growth("2026-10-15", "2026-11-14", MB, MB / 3), 760, 150);
		expect(chart).not.toBeNull();
		const actual = points(chart?.actual ?? "");
		const ahead = points(chart?.ahead ?? "");
		// The dashed line starts where the drawn one ends, and the newest day
		// is halfway: 90 days kept, 90 carried forward.
		expect(ahead[0]).toEqual(actual[actual.length - 1]);
		expect(chart?.now.x).toBeCloseTo(380, 0);
		expect(chart?.end).toEqual({ day: "2027-02-12", bytes: 4 * MB });
		expect(chart?.labels.map((l) => l.text)).toEqual(["Aug 2026", "Nov", "Feb 2027"]);
	});

	it("carries a few days' pace a month at least, and a long history's a year at most", () => {
		const short = sizeChart(
			[size("2026-11-12", 3), size("2026-11-14", 3.1)],
			growth("2026-11-12", "2026-11-14", 0.1 * MB, 1.5 * MB),
			760,
			150,
		);
		expect(short?.end?.day).toBe("2026-12-14");
		// Days, not months, on a short axis; the newest day's label has no
		// room beside the first's and is left out.
		expect(short?.labels.map((l) => l.text)).toEqual(["12 Nov", "14 Dec"]);
		const long = sizeChart(
			[size("2025-01-01", 1), size("2026-11-14", 3)],
			growth("2026-10-15", "2026-11-14", MB, MB),
			760,
			150,
		);
		expect(long?.end?.day).toBe("2027-11-14");
	});

	it("never carries a shrinking database below nothing", () => {
		const chart = sizeChart(
			[size("2026-11-01", 2), size("2026-11-14", 1)],
			growth("2026-11-01", "2026-11-14", -MB, -3 * MB),
			760,
			150,
		);
		expect(chart?.end?.bytes).toBe(0);
		for (const [, y] of points(chart?.ahead ?? "")) expect(y).toBeLessThanOrEqual(150);
	});

	it("puts the lowest size at the bottom and the highest at the top of the box", () => {
		const chart = sizeChart(
			[size("2026-11-01", 1), size("2026-11-07", 3), size("2026-11-14", 2)],
			null,
			760,
			150,
		);
		const ys = (chart?.points ?? []).map((p) => p.y);
		expect(Math.max(...ys)).toBe(ys[0]);
		expect(Math.min(...ys)).toBe(ys[1]);
		expect(chart?.ahead).toBe("");
	});
});

describe("the coach's cost by model", () => {
	it("names a model's family, and anything unnamed as Other", () => {
		expect(familyOf("claude-sonnet-4-6")).toBe("Sonnet");
		expect(familyOf("claude-haiku-4-5-20251001")).toBe("Haiku");
		expect(familyOf("some-new-model")).toBe("Other");
	});

	it("stacks a day's families in the fixed order, keeping only those in the days shown", () => {
		const { families, days } = dailyCostByFamily(
			[
				cost("2026-11-14", "claude-haiku-4-5", 0.5),
				cost("2026-11-14", "claude-sonnet-5-5", 2),
				cost("2026-11-14", "claude-sonnet-4-6", 1),
				cost("2026-11-13", "claude-sonnet-5-5", 4),
				// Outside the two days shown.
				cost("2026-11-01", "claude-opus-5", 90),
			],
			2,
			NOON_14TH,
		);
		expect(families.map((f) => f.family)).toEqual(["Sonnet", "Haiku"]);
		expect(days).toEqual([
			{ day: "2026-11-13", total: 4, parts: [4, 0] },
			{ day: "2026-11-14", total: 3.5, parts: [3, 0.5] },
		]);
	});

	it("keeps a family's colour whichever families are shown", () => {
		const alone = dailyCostByFamily([cost("2026-11-14", "claude-haiku-4-5", 1)], 7, NOON_14TH);
		const haiku = MODEL_FAMILIES.find((f) => f.family === "Haiku");
		expect(alone.families).toEqual([haiku]);
	});
});
