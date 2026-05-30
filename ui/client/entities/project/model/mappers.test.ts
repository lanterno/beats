import { describe, expect, it } from "vitest";
import type { ApiProject } from "@/shared/api";
import { toApiProject, toProject } from "./mappers";

describe("Project mapper round-trip", () => {
	it("preserves the previously-invisible fields across toProject → toApiProject", () => {
		// P1.1 guard: without these mapped, any form using updateProject would
		// PUT { github_repo: undefined } and the backend would clobber the value
		// — the exact silent-wipe bug class the contract revamp is fixing.
		const fromWire: ApiProject = {
			id: "p1",
			name: "Alpha",
			description: "x",
			color: "#FBBF24",
			archived: false,
			estimation: null,
			weekly_goal: 10,
			goal_type: "target",
			goal_overrides: [],
			github_repo: "lanterno/beats",
			category: "coding",
			autostart_repos: ["/Users/me/code/beats"],
		};

		const domain = toProject(fromWire);
		expect(domain.githubRepo).toBe("lanterno/beats");
		expect(domain.category).toBe("coding");
		expect(domain.autostartRepos).toEqual(["/Users/me/code/beats"]);

		const backToWire = toApiProject(domain);
		expect(backToWire.github_repo).toBe("lanterno/beats");
		expect(backToWire.category).toBe("coding");
		expect(backToWire.autostart_repos).toEqual(["/Users/me/code/beats"]);
	});

	it("normalizes absent values: undefined on the domain side, null/[] on the wire", () => {
		const fromWire: ApiProject = {
			id: "p2",
			name: "Beta",
			archived: false,
			goal_type: "target",
			goal_overrides: [],
			autostart_repos: [],
		};
		const domain = toProject(fromWire);
		expect(domain.githubRepo).toBeUndefined();
		expect(domain.category).toBeUndefined();
		expect(domain.autostartRepos).toEqual([]);

		const backToWire = toApiProject(domain);
		expect(backToWire.github_repo).toBeNull();
		expect(backToWire.category).toBeNull();
		expect(backToWire.autostart_repos).toEqual([]);
	});
});
