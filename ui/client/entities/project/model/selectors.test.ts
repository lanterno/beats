import { describe, expect, it } from "vitest";
import {
	filterAndRankProjects,
	isVisibleProject,
	partitionByArchived,
	sortProjectsForList,
	visibleProjects,
} from "./selectors";

const active = { archived: false } as const;
const archived = { archived: true } as const;

describe("isVisibleProject", () => {
	it("hides archived, keeps everything else", () => {
		expect(isVisibleProject(active)).toBe(true);
		expect(isVisibleProject(archived)).toBe(false);
	});
});

describe("visibleProjects", () => {
	it("returns only the non-archived projects", () => {
		const list = [active, archived, active];
		expect(visibleProjects(list)).toEqual([active, active]);
	});

	it("handles undefined input — every consumer that hits a loading state", () => {
		expect(visibleProjects(undefined)).toEqual([]);
	});
});

describe("partitionByArchived", () => {
	it("splits projects into visible vs archived buckets", () => {
		const list = [
			{ id: "p1", archived: false },
			{ id: "p2", archived: true },
			{ id: "p3", archived: false },
		];
		expect(partitionByArchived(list)).toEqual({
			visible: [
				{ id: "p1", archived: false },
				{ id: "p3", archived: false },
			],
			archived: [{ id: "p2", archived: true }],
		});
	});

	it("returns empty buckets for undefined input", () => {
		expect(partitionByArchived(undefined)).toEqual({ visible: [], archived: [] });
	});
});

describe("sortProjectsForList", () => {
	it("places active (weeklyMinutes > 0) projects first, sorted by weekly minutes desc", () => {
		const list = [
			{ name: "Cold", weeklyMinutes: 0 },
			{ name: "Hot", weeklyMinutes: 300 },
			{ name: "Warm", weeklyMinutes: 100 },
			{ name: "Frozen", weeklyMinutes: 0 },
		];
		expect(sortProjectsForList(list).map((p) => p.name)).toEqual([
			"Hot",
			"Warm",
			"Cold", // inactive — alphabetical
			"Frozen",
		]);
	});

	it("handles an empty list without crashing", () => {
		expect(sortProjectsForList([])).toEqual([]);
	});
});

describe("filterAndRankProjects", () => {
	const alpha = { id: "a", name: "Alpha", description: "first project", archived: false };
	const beta = { id: "b", name: "Beta", description: "the second one", archived: false };
	const gamma = { id: "g", name: "Gamma", description: undefined, archived: false };
	const old = { id: "o", name: "OldAlpha", description: "retired", archived: true };
	const all = [alpha, beta, gamma, old];

	it("hides archived by default", () => {
		expect(filterAndRankProjects(all, "")).toEqual([alpha, beta, gamma]);
	});

	it("includes archived when showArchived=true", () => {
		expect(filterAndRankProjects(all, "", { showArchived: true })).toEqual([
			alpha,
			beta,
			gamma,
			old,
		]);
	});

	it("substring-matches name and description case-insensitively", () => {
		expect(filterAndRankProjects(all, "alp")).toEqual([alpha]);
		expect(filterAndRankProjects(all, "SECOND")).toEqual([beta]);
		// gamma has no description; the filter must not throw and just skips it.
		expect(filterAndRankProjects(all, "no-match")).toEqual([]);
	});

	it("honors a narrowed searchFields list", () => {
		// 'first project' would match alpha by description, but with name-only
		// the query has to hit the name.
		expect(filterAndRankProjects(all, "first project", { searchFields: ["name"] })).toEqual([]);
		expect(filterAndRankProjects(all, "alp", { searchFields: ["name"] })).toEqual([alpha]);
	});

	it("surfaces recents at the top with no query — recents not in list are dropped", () => {
		expect(filterAndRankProjects(all, "", { recents: ["b", "ZZ-missing", "a"] })).toEqual([
			beta,
			alpha,
			gamma,
		]);
	});

	it("ignores recents once the user is typing", () => {
		// With a query the user is driving the order; recents would be confusing.
		expect(filterAndRankProjects(all, "alp", { recents: ["b"] })).toEqual([alpha]);
	});
});
