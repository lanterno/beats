/**
 * What a list surface shows as "this week" for a project: hours against a
 * goal, and — on a day job the contract governs — the running balance.
 *
 * The contract path reads the list's contract fields (the API's week
 * against the contract, adjusted for holidays and absences) and its own
 * worked figure, which counts every beat by local day, a running timer
 * included. Every other project keeps the personal goal's path exactly as
 * it was: `weekly_minutes` (completed beats by UTC day) against the
 * resolved effective goal, honouring an override that says "no goal".
 */

import type { ProjectWithDuration } from "./types";

export interface WeekGoalView {
	/** Hours worked this week. */
	hours: number;
	/** Hours the week asks for; null when nothing sets a goal. */
	goal: number | null;
	goalType: "target" | "cap";
	/** Running balance against the contract, as of today; null off the contract path. */
	balance: number | null;
	source: "contract" | "personal";
}

export function weekGoalView(project: ProjectWithDuration): WeekGoalView {
	// `contractExpected` is undefined under an objective term and before the
	// contract starts — exactly the weeks the API resolves the personal goal
	// for, so those fall through to it.
	if (project.kind === "day_job" && project.contractExpected !== undefined) {
		return {
			hours: project.contractWorked ?? 0,
			goal: project.contractExpected,
			goalType: "target",
			balance: project.balance ?? null,
			source: "contract",
		};
	}
	// effectiveGoal === null with overridden === true is an override saying
	// "no goal": do not fall back to the project default then.
	const goal = project.effectiveGoalOverridden
		? (project.effectiveGoal ?? null)
		: (project.effectiveGoal ?? project.weeklyGoal ?? null);
	return {
		hours: project.weeklyMinutes / 60,
		goal,
		goalType: project.effectiveGoalType ?? project.goalType ?? "target",
		balance: null,
		source: "personal",
	};
}
