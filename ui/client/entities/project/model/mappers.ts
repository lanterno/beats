/**
 * Project Mappers
 * Convert between API types and domain types.
 */
import type { ApiGoalOverride, ApiProject } from "@/shared/api";
import { assignColor } from "./colors";
import type { GoalOverride, Project } from "./types";

/**
 * Convert API project to domain Project
 */
export function toProject(apiProject: ApiProject): Project {
	const id = apiProject.id || "";
	return {
		id,
		name: apiProject.name,
		description: apiProject.description ?? undefined,
		color: apiProject.color || assignColor(id),
		archived: apiProject.archived ?? false,
		estimation: apiProject.estimation ?? undefined,
		weeklyGoal: apiProject.weekly_goal ?? undefined,
		goalType: apiProject.goal_type ?? "target",
		goalOverrides: (apiProject.goal_overrides ?? []).map(toGoalOverride),
	};
}

/**
 * Convert domain Project to API format
 */
export function toApiProject(project: Project): ApiProject {
	return {
		id: project.id,
		name: project.name,
		description: project.description ?? null,
		color: project.color ?? null,
		archived: project.archived,
		estimation: project.estimation ?? null,
		weekly_goal: project.weeklyGoal ?? null,
		goal_type: project.goalType ?? "target",
		goal_overrides: (project.goalOverrides ?? []).map(toApiGoalOverride),
	};
}

function toGoalOverride(api: ApiGoalOverride): GoalOverride {
	return {
		weekOf: api.week_of ?? undefined,
		effectiveFrom: api.effective_from ?? undefined,
		weeklyGoal: api.weekly_goal,
		goalType: api.goal_type ?? undefined,
		note: api.note ?? undefined,
	};
}

function toApiGoalOverride(o: GoalOverride): ApiGoalOverride {
	return {
		week_of: o.weekOf ?? null,
		effective_from: o.effectiveFrom ?? null,
		weekly_goal: o.weeklyGoal,
		goal_type: o.goalType ?? null,
		note: o.note ?? null,
	};
}
