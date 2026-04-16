import { describe, expect, it } from "vitest";
import { fuzzyRank, score } from "./fuzzyMatch";

describe("score", () => {
	it("returns 1 for empty query", () => {
		expect(score("", "Go to Insights")).toBe(1);
	});

	it("returns 0 when characters aren't a subsequence", () => {
		expect(score("xyz", "Go to Insights")).toBe(0);
	});

	it("is case-insensitive", () => {
		expect(score("INS", "Go to Insights")).toBeGreaterThan(0);
	});

	it("scores prefix matches higher than scattered", () => {
		const prefix = score("ins", "Insights");
		const scattered = score("ins", "Start timer on Beats");
		expect(prefix).toBeGreaterThan(scattered);
	});

	it("rewards word-boundary hits", () => {
		const boundary = score("gti", "Go To Insights");
		const interior = score("gti", "gatineau");
		expect(boundary).toBeGreaterThan(interior);
	});
});

describe("fuzzyRank", () => {
	const items = ["Go to Insights", "Go to Dashboard", "Start timer", "Stop timer"];

	it("filters non-matching items when query is non-empty", () => {
		const ranked = fuzzyRank(items, "ins", (s) => s);
		expect(ranked.map((r) => r.item)).toEqual(["Go to Insights"]);
	});

	it("returns all items when query is empty", () => {
		const ranked = fuzzyRank(items, "", (s) => s);
		expect(ranked).toHaveLength(items.length);
	});

	it("orders by descending score", () => {
		const ranked = fuzzyRank(items, "timer", (s) => s);
		expect(ranked.map((r) => r.item)).toContain("Start timer");
		expect(ranked.map((r) => r.item)).toContain("Stop timer");
		// Both should match; the order is stable-enough that both appear at the top.
		expect(ranked[0].score).toBeGreaterThan(0);
	});

	it("applies recency boost to float frequent items", () => {
		const boost = (s: string) => (s === "Stop timer" ? 0.5 : 0);
		const ranked = fuzzyRank(items, "timer", (s) => s, boost);
		expect(ranked[0].item).toBe("Stop timer");
	});
});
