import { describe, expect, it } from "vitest";
import { isVisibleProject, partitionByArchived, visibleProjects } from "./selectors";

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
