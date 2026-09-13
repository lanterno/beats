/**
 * The personal goal a project stands at on a given Monday. A permanent
 * override (`effectiveFrom`) replaces the project's own goal from its date
 * on; a one-week override (`weekOf`) bends a single week and leaves the
 * standing goal alone. The header's kind chip and the Goal panel both read
 * it here, so the two cannot name different figures.
 */

import type { GoalOverride, Project } from "./types";

/** The permanent override in effect on a Monday: the latest one dated on or before it. */
export function permanentOverrideOn(
	overrides: readonly GoalOverride[],
	mondayIso: string,
): GoalOverride | undefined {
	let found: GoalOverride | undefined;
	for (const o of overrides) {
		if (!o.effectiveFrom || o.effectiveFrom > mondayIso) continue;
		if (!found || o.effectiveFrom > (found.effectiveFrom ?? "")) found = o;
	}
	return found;
}

export interface StandingGoal {
	/** Hours a week; null when an override says "no goal" or none was ever set. */
	weeklyGoal: number | null;
	goalType: "target" | "cap";
	/** The permanent override that sets it, if one does. */
	override?: GoalOverride;
}

/** The goal in force on a Monday: the permanent override then, else the project's own. */
export function standingGoalOn(
	project: Pick<Project, "weeklyGoal" | "goalType" | "goalOverrides">,
	mondayIso: string,
): StandingGoal {
	const override = permanentOverrideOn(project.goalOverrides ?? [], mondayIso);
	const goalType = override?.goalType ?? project.goalType ?? "target";
	return override
		? { weeklyGoal: override.weeklyGoal, goalType, override }
		: { weeklyGoal: project.weeklyGoal ?? null, goalType };
}
