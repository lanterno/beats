import { describe, expect, it } from "vitest";
import type { FlowWindow } from "@/shared/api";
import {
	aggregateFlowBy,
	aggregateFlowByDay,
	aggregateFlowByRepo,
	flowBaseline,
	localDateKey,
	shortRepoPath,
	summarizeFlow,
} from "./flowAggregation";

// Helper: build a FlowWindow with sensible defaults plus the fields the
// aggregation actually reads. Keeps the test bodies focused on the
// per-case overrides without 12 lines of zeros each.
function w(overrides: Partial<FlowWindow> = {}): FlowWindow {
	return {
		id: Math.random().toString(36).slice(2),
		window_start: "2026-04-30T09:00:00Z",
		window_end: "2026-04-30T09:01:00Z",
		flow_score: 0.5,
		cadence_score: 0.5,
		coherence_score: 0.5,
		category_fit_score: 0.5,
		idle_fraction: 0,
		dominant_bundle_id: "",
		dominant_category: "",
		context_switches: 0,
		active_project_id: null,
		editor_repo: null,
		editor_branch: null,
		editor_language: null,
		...overrides,
	};
}

describe("aggregateFlowByRepo", () => {
	it("returns an empty array when there are no windows", () => {
		expect(aggregateFlowByRepo([])).toEqual([]);
	});

	it("returns an empty array when no window has an editor_repo", () => {
		const windows = [w({ flow_score: 0.9 }), w({ flow_score: 0.8 })];
		expect(aggregateFlowByRepo(windows)).toEqual([]);
	});

	it("groups by repo and computes the unweighted mean score", () => {
		const windows = [
			w({ flow_score: 0.6, editor_repo: "/a" }),
			w({ flow_score: 0.8, editor_repo: "/a" }),
			w({ flow_score: 1.0, editor_repo: "/b" }),
		];
		const stats = aggregateFlowByRepo(windows);
		const a = stats.find((s) => s.repo === "/a");
		const b = stats.find((s) => s.repo === "/b");
		expect(a?.avg).toBeCloseTo(0.7);
		expect(a?.minutes).toBe(2);
		expect(b?.avg).toBeCloseTo(1.0);
		expect(b?.minutes).toBe(1);
	});

	it("sorts by minutes (window count) descending", () => {
		const windows = [
			w({ editor_repo: "/c" }),
			w({ editor_repo: "/c" }),
			w({ editor_repo: "/c" }),
			w({ editor_repo: "/a" }),
			w({ editor_repo: "/b" }),
			w({ editor_repo: "/b" }),
		];
		const stats = aggregateFlowByRepo(windows);
		expect(stats.map((s) => s.repo)).toEqual(["/c", "/b", "/a"]);
	});

	it("respects the limit parameter", () => {
		const windows: FlowWindow[] = [];
		for (let i = 0; i < 10; i++) {
			// Each repo gets a different count so they sort deterministically.
			for (let j = 0; j <= i; j++) windows.push(w({ editor_repo: `/repo-${i}` }));
		}
		expect(aggregateFlowByRepo(windows, 3).length).toBe(3);
		expect(aggregateFlowByRepo(windows, 3).map((s) => s.repo)).toEqual([
			"/repo-9",
			"/repo-8",
			"/repo-7",
		]);
	});

	it("skips windows with empty-string editor_repo", () => {
		const windows = [w({ editor_repo: "" }), w({ editor_repo: "/a" })];
		const stats = aggregateFlowByRepo(windows);
		expect(stats).toHaveLength(1);
		expect(stats[0].repo).toBe("/a");
	});
});

describe("aggregateFlowBy (generic)", () => {
	it("groups by an arbitrary keyOf function — language", () => {
		const windows = [
			w({ flow_score: 0.5, editor_language: "go" }),
			w({ flow_score: 0.7, editor_language: "go" }),
			w({ flow_score: 0.9, editor_language: "rust" }),
		];
		const stats = aggregateFlowBy(windows, (win) => win.editor_language);
		expect(stats).toHaveLength(2);
		const go = stats.find((s) => s.key === "go");
		expect(go?.avg).toBeCloseTo(0.6);
		expect(go?.minutes).toBe(2);
	});

	it("groups by dominant_category", () => {
		const windows = [
			w({ flow_score: 0.4, dominant_category: "browser" }),
			w({ flow_score: 0.8, dominant_category: "coding" }),
			w({ flow_score: 0.9, dominant_category: "coding" }),
		];
		const stats = aggregateFlowBy(windows, (win) => win.dominant_category);
		expect(stats[0].key).toBe("coding"); // sorts by minute count
		expect(stats[0].minutes).toBe(2);
	});

	it("skips windows where keyOf returns undefined / null / empty", () => {
		const windows = [
			w({ editor_language: undefined }),
			w({ editor_language: null }),
			w({ editor_language: "" }),
			w({ editor_language: "go" }),
		];
		const stats = aggregateFlowBy(windows, (win) => win.editor_language);
		expect(stats).toHaveLength(1);
		expect(stats[0].key).toBe("go");
	});
});

describe("aggregateFlowByDay", () => {
	it("returns an empty array for no windows", () => {
		expect(aggregateFlowByDay([])).toEqual([]);
	});

	it("groups windows by local date and averages within each", () => {
		// Three windows on Apr 30 (avg 0.6), two on Apr 29 (avg 0.5). Use
		// noon-local to avoid timezone-flip ambiguity.
		const windows = [
			w({ window_start: "2026-04-29T12:00:00Z", flow_score: 0.4 }),
			w({ window_start: "2026-04-29T12:00:00Z", flow_score: 0.6 }),
			w({ window_start: "2026-04-30T12:00:00Z", flow_score: 0.5 }),
			w({ window_start: "2026-04-30T12:00:00Z", flow_score: 0.6 }),
			w({ window_start: "2026-04-30T12:00:00Z", flow_score: 0.7 }),
		];
		const byDay = aggregateFlowByDay(windows);
		expect(byDay).toHaveLength(2);
		// Sorted by date ascending — older first.
		expect(byDay[0].count).toBe(2);
		expect(byDay[0].avg).toBeCloseTo(0.5);
		expect(byDay[1].count).toBe(3);
		expect(byDay[1].avg).toBeCloseTo(0.6);
	});

	it("does NOT backfill empty days — caller decides", () => {
		const windows = [
			w({ window_start: "2026-04-29T12:00:00Z", flow_score: 0.5 }),
			w({ window_start: "2026-05-01T12:00:00Z", flow_score: 0.7 }),
		];
		const byDay = aggregateFlowByDay(windows);
		// Apr 30 is missing — that's intentional so a 7-day chart can choose
		// to render it as "0" or as a gap.
		expect(byDay).toHaveLength(2);
	});
});

describe("flowBaseline", () => {
	const today = new Date(2026, 3, 30); // Apr 30, 2026 (local)

	it("returns null when not enough prior windows exist", () => {
		// 5 prior-day windows; minWindows defaults to 30. Should return null
		// so callers don't draw a comparison off too little data.
		const windows: ReturnType<typeof w>[] = [];
		for (let i = 0; i < 5; i++) {
			windows.push(w({ window_start: "2026-04-29T12:00:00Z", flow_score: 0.7 }));
		}
		expect(flowBaseline(windows, today)).toBeNull();
	});

	it("excludes today's windows from the baseline", () => {
		const prior: ReturnType<typeof w>[] = [];
		for (let i = 0; i < 30; i++) {
			prior.push(w({ window_start: "2026-04-29T12:00:00Z", flow_score: 0.5 }));
		}
		const todays = [w({ window_start: "2026-04-30T12:00:00Z", flow_score: 0.95 })];
		const baseline = flowBaseline([...prior, ...todays], today);
		// Today's 0.95 must NOT pull the baseline up.
		expect(baseline).toBeCloseTo(0.5);
	});

	it("returns the unweighted mean across qualifying windows", () => {
		const windows: ReturnType<typeof w>[] = [];
		// 20 windows at 0.4, 20 windows at 0.6 → mean 0.5.
		for (let i = 0; i < 20; i++) {
			windows.push(w({ window_start: "2026-04-28T12:00:00Z", flow_score: 0.4 }));
		}
		for (let i = 0; i < 20; i++) {
			windows.push(w({ window_start: "2026-04-29T12:00:00Z", flow_score: 0.6 }));
		}
		expect(flowBaseline(windows, today)).toBeCloseTo(0.5);
	});

	it("respects a custom minWindows threshold", () => {
		const windows = [w({ window_start: "2026-04-29T12:00:00Z", flow_score: 0.7 })];
		expect(flowBaseline(windows, today, 1)).toBeCloseTo(0.7);
		expect(flowBaseline(windows, today, 2)).toBeNull();
	});
});

describe("localDateKey", () => {
	it("returns YYYY-MM-DD in local time", () => {
		// Use a time mid-afternoon UTC so the local date can't possibly
		// flip across timezones — Apr 30 12:00 UTC is Apr 30 in every
		// reasonable runner timezone.
		expect(localDateKey("2026-04-30T12:00:00Z")).toBe("2026-04-30");
	});

	it("zero-pads month and day", () => {
		expect(localDateKey("2026-01-05T12:00:00Z")).toBe("2026-01-05");
	});
});

describe("shortRepoPath", () => {
	it("returns the path unchanged when it has fewer segments than requested", () => {
		expect(shortRepoPath("only", 2)).toBe("only");
	});

	it("returns the last two segments by default", () => {
		expect(shortRepoPath("/Users/me/code/example")).toBe("code/example");
	});

	it("respects the segments parameter", () => {
		expect(shortRepoPath("/Users/me/code/example", 1)).toBe("example");
		expect(shortRepoPath("/Users/me/code/example", 3)).toBe("me/code/example");
	});

	it("handles Windows-style backslashes", () => {
		expect(shortRepoPath("C:\\Users\\me\\code\\example")).toBe("code/example");
	});

	it("returns the original path when empty", () => {
		expect(shortRepoPath("")).toBe("");
	});
});

describe("summarizeFlow", () => {
	it("returns null for empty input", () => {
		expect(summarizeFlow([])).toBeNull();
	});

	it("computes avg, peak, count, and peakIndex", () => {
		const windows = [w({ flow_score: 0.2 }), w({ flow_score: 0.6 }), w({ flow_score: 0.9 })];
		const s = summarizeFlow(windows);
		expect(s?.count).toBe(3);
		expect(s?.peak).toBe(0.9);
		expect(s?.avg).toBeCloseTo(0.5666, 3);
		expect(s?.peakIndex).toBe(2);
	});

	it("treats a single window correctly", () => {
		const s = summarizeFlow([w({ flow_score: 0.42 })]);
		expect(s).toEqual({ avg: 0.42, peak: 0.42, count: 1, peakIndex: 0 });
	});

	it("returns the earliest index on tied peaks", () => {
		// Three windows tied at 0.9. peakIndex should point at the first
		// one — earliest-peak framing reads as "this is when you locked in"
		// rather than "the day got worse since".
		const windows = [
			w({ flow_score: 0.5 }),
			w({ flow_score: 0.9 }),
			w({ flow_score: 0.9 }),
			w({ flow_score: 0.6 }),
			w({ flow_score: 0.9 }),
		];
		expect(summarizeFlow(windows)?.peakIndex).toBe(1);
	});
});
