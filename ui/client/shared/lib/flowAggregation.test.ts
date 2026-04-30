import { describe, expect, it } from "vitest";
import type { FlowWindow } from "@/shared/api";
import {
	aggregateFlowBy,
	aggregateFlowByRepo,
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

	it("computes avg, peak, and count", () => {
		const windows = [w({ flow_score: 0.2 }), w({ flow_score: 0.6 }), w({ flow_score: 0.9 })];
		const s = summarizeFlow(windows);
		expect(s?.count).toBe(3);
		expect(s?.peak).toBe(0.9);
		expect(s?.avg).toBeCloseTo(0.5666, 3);
	});

	it("treats a single window correctly", () => {
		const s = summarizeFlow([w({ flow_score: 0.42 })]);
		expect(s).toEqual({ avg: 0.42, peak: 0.42, count: 1 });
	});
});
