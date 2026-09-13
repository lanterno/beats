/**
 * The step chart's geometry: which stretch is solid and which dashed around
 * today, the risers between steps, a gap for a step of no hours, the chart
 * stopping at `endedOn`, and what each step and the axis are labelled.
 */
import { describe, expect, it } from "vitest";
import { CHART_WIDTH, stepChartGeometry } from "./stepChart";

// The mockup's register: 60 % from Jan 5, 80 % from Aug 3, 100 % planned for Jan 4 2027.
const MOCKUP = [
	{ date: "2026-01-05", hours: 25.2, label: "60% · 25.2 h" },
	{ date: "2026-08-03", hours: 33.6, label: "80% · 33.6 h" },
	{ date: "2027-01-04", hours: 42, label: "100% · 42 h" },
];

describe("stepChartGeometry", () => {
	it("draws solid through today and dashed after it, the planned step dashed with its riser", () => {
		const chart = stepChartGeometry({ steps: MOCKUP, todayIso: "2026-09-10" });
		if (!chart) throw new Error("no chart");
		const { segments, today } = chart;

		expect(segments.map((s) => s.kind)).toEqual([
			"solid", // Jan 5 → Aug 3 at 25.2
			"solid", // the riser on Aug 3
			"solid", // Aug 3 → today at 33.6
			"dashed", // today → Jan 4, the 80 % term continuing
			"dashed", // the riser into the planned term
			"dashed", // Jan 4 → the chart's end at 42
		]);
		expect(today).not.toBeNull();
		expect(segments[2].x2).toBe(today?.x);
		expect(segments[3].x1).toBe(today?.x);
		// The riser climbs; the planned term is the top of the chart.
		expect(segments[1].y2).toBeLessThan(segments[1].y1);
		expect(segments[5].y1).toBe(Math.min(...segments.map((s) => s.y1)));
		// Six months past the last step outruns three months past today.
		expect(segments[5].x2).toBe(CHART_WIDTH - 4);
		// One meadow under the solid run, closed on the axis.
		expect(chart.areas).toHaveLength(1);
		expect(chart.areas[0]).toMatch(new RegExp(`L${today?.x},${segments[2].y1}L${today?.x},`));

		expect(chart.labels.map((l) => l.text)).toEqual([
			"60% · 25.2 h",
			"80% · 33.6 h",
			"100% · 42 h",
		]);
		expect(chart.axis.map((a) => a.text)).toEqual(["Jan 5 ’26", "Aug 3", "Jan 4 ’27"]);
	});

	it("keeps the step in force labelled and dated where steps crowd, and thins the rest", () => {
		const chart = stepChartGeometry({
			steps: [
				{ date: "2026-01-05", hours: 25.2, label: "60% · 25.2 h" },
				// Two weeks at 50 %: its line, but no label and no date.
				{ date: "2026-03-02", hours: 21, label: "50% · 21 h" },
				{ date: "2026-03-16", hours: 25.2, label: "60% again" },
				// In force and five weeks short; the 70 % step just after it gives way.
				{ date: "2026-08-31", hours: 33.6, label: "80% · 33.6 h" },
				{ date: "2026-10-05", hours: 29.4, label: "70% · 29.4 h" },
				{ date: "2027-01-04", hours: 42, label: "100% · 42 h" },
			],
			todayIso: "2026-09-10",
		});
		if (!chart) throw new Error("no chart");

		expect(chart.labels.map((l) => l.text)).toEqual(["60% again", "80% · 33.6 h", "100% · 42 h"]);
		expect(chart.axis.map((a) => a.text)).toEqual(["Jan 5 ’26", "Mar 16", "Aug 31", "Jan 4 ’27"]);
		const horizontals = chart.segments.filter((s) => s.y1 === s.y2);
		const lowest = Math.max(...horizontals.map((s) => s.y1));
		expect(horizontals.filter((s) => s.y1 === lowest)).toHaveLength(1);

		// Here the step in force begins close after a short one: its date wins.
		const close = stepChartGeometry({
			steps: [
				{ date: "2026-01-05", hours: 42, label: "100% · 42 h" },
				{ date: "2026-07-20", hours: 21, label: "50% · 21 h" },
				{ date: "2026-08-17", hours: 33.6, label: "80% · 33.6 h" },
			],
			todayIso: "2026-09-10",
		});
		expect(close?.axis.map((a) => a.text)).toEqual(["Jan 5 ’26", "Aug 17"]);
	});

	it("leaves a labelled gap for a step of no hours and puts a step at zero on the axis", () => {
		const chart = stepChartGeometry({
			steps: [
				{ date: "2026-01-05", hours: 32, label: "32 h" },
				{ date: "2026-03-02", hours: null, label: "objective" },
				{ date: "2026-05-04", hours: 0, label: "0 h" },
				{ date: "2026-07-06", hours: 20, label: "20 h" },
			],
			todayIso: "2026-09-10",
		});
		if (!chart) throw new Error("no chart");

		const horizontals = chart.segments.filter((s) => s.y1 === s.y2);
		// No line across the gap: 32 h, 0 h, 20 h through today, 20 h after.
		expect(horizontals.map((s) => s.kind)).toEqual(["solid", "solid", "solid", "dashed"]);
		expect(horizontals[1].y1).toBe(chart.baseline);
		// Only the rise from 0 to 20 h: nothing climbs into or out of the gap.
		expect(chart.segments.filter((s) => s.x1 === s.x2)).toHaveLength(1);
		expect(chart.areas).toHaveLength(2);

		const gap = chart.labels.find((l) => l.text === "objective");
		const zero = chart.labels.find((l) => l.text === "0 h");
		expect(gap?.y).toBeLessThan(chart.baseline);
		expect(zero?.y).toBeLessThan(chart.baseline);
	});

	it("stops at ended_on, solid to the end, with no today marker past it", () => {
		const chart = stepChartGeometry({
			steps: [
				{ date: "2026-01-05", hours: 42, label: "100% · 42 h" },
				{ date: "2026-04-06", hours: 33.6, label: "80% · 33.6 h" },
			],
			todayIso: "2026-09-10",
			endedOn: "2026-08-31",
		});
		if (!chart) throw new Error("no chart");

		expect(chart.segments.every((s) => s.kind === "solid")).toBe(true);
		expect(chart.segments[chart.segments.length - 1].x2).toBe(CHART_WIDTH - 4);
		expect(chart.today).toBeNull();
	});

	it("dashes a contract that has not started yet and grows no meadow", () => {
		const chart = stepChartGeometry({
			steps: [
				{ date: "2026-10-05", hours: 42, label: "100% · 42 h" },
				{ date: "2027-01-04", hours: 33.6, label: "80% · 33.6 h" },
			],
			todayIso: "2026-09-10",
		});
		if (!chart) throw new Error("no chart");

		expect(chart.segments.every((s) => s.kind === "dashed")).toBe(true);
		expect(chart.areas).toEqual([]);
		expect(chart.today).toBeNull();
	});
});
