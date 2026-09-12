import { describe, expect, it } from "vitest";
import type { ProjectWithDuration } from "./types";
import { weekGoalView } from "./weekGoal";

function project(overrides: Partial<ProjectWithDuration>): ProjectWithDuration {
	return {
		id: "p",
		name: "P",
		color: "#888",
		archived: false,
		goalOverrides: [],
		autostartRepos: [],
		kind: "side_project",
		totalMinutes: 0,
		weeklyMinutes: 0,
		...overrides,
	};
}

describe("weekGoalView", () => {
	it("reads a governed day job's week from the contract, balance included", () => {
		// weekly_minutes and the nominal effective goal sit beside the contract
		// fields on the wire; a governed week reads none of them.
		const view = weekGoalView(
			project({
				kind: "day_job",
				weeklyMinutes: 600,
				effectiveGoal: 40,
				contractExpected: 32,
				contractWorked: 12.5,
				contractRemaining: 19.5,
				balance: -2,
			}),
		);
		expect(view).toEqual({
			hours: 12.5,
			goal: 32,
			goalType: "target",
			balance: -2,
			source: "contract",
		});
	});

	it("keeps a side project on the personal goal's path: minutes, effective goal and type", () => {
		const view = weekGoalView(
			project({
				weeklyMinutes: 90,
				weeklyGoal: 10,
				effectiveGoal: 8,
				effectiveGoalType: "cap",
				effectiveGoalOverridden: true,
			}),
		);
		expect(view).toEqual({
			hours: 1.5,
			goal: 8,
			goalType: "cap",
			balance: null,
			source: "personal",
		});
	});

	it("honours an override that says no goal rather than falling back to the default", () => {
		const view = weekGoalView(
			project({
				weeklyMinutes: 60,
				weeklyGoal: 10,
				effectiveGoal: null,
				effectiveGoalOverridden: true,
			}),
		);
		expect(view.goal).toBeNull();
	});

	it("keeps the personal goal on a day job the contract does not govern", () => {
		// An objective term: the API reports the contract's worked hours but no
		// expectation and no balance, and resolves the personal goal.
		const view = weekGoalView(
			project({
				kind: "day_job",
				weeklyMinutes: 120,
				weeklyGoal: 20,
				effectiveGoal: 20,
				contractWorked: 2.5,
			}),
		);
		expect(view).toMatchObject({ hours: 2, goal: 20, balance: null, source: "personal" });
	});
});
