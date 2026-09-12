/**
 * Project Mappers
 * Convert between API types and domain types.
 */
import type { ApiContract, ApiContractTerm, ApiGoalOverride, ApiProject } from "@/shared/api";
import { assignColor } from "./colors";
import type { Contract, ContractTerm, GoalOverride, Project } from "./types";

export function toProject(apiProject: ApiProject): Project {
	const id = apiProject.id || "";
	return {
		id,
		name: apiProject.name,
		description: apiProject.description ?? undefined,
		color: apiProject.color || assignColor(id),
		archived: apiProject.archived ?? false,
		weeklyGoal: apiProject.weekly_goal ?? undefined,
		goalType: apiProject.goal_type ?? "target",
		goalOverrides: (apiProject.goal_overrides ?? []).map(toGoalOverride),
		githubRepo: apiProject.github_repo ?? undefined,
		category: apiProject.category ?? undefined,
		autostartRepos: apiProject.autostart_repos ?? [],
		kind: apiProject.kind ?? "side_project",
		// A contract only means something on a day job; the API never stores
		// one elsewhere, and reading one here would let the UI show it.
		contract:
			apiProject.kind === "day_job" && apiProject.contract
				? toContract(apiProject.contract)
				: undefined,
	};
}

export function toApiProject(project: Project): ApiProject {
	return {
		id: project.id,
		name: project.name,
		description: project.description ?? null,
		color: project.color ?? null,
		archived: project.archived,
		weekly_goal: project.weeklyGoal ?? null,
		goal_type: project.goalType ?? "target",
		goal_overrides: (project.goalOverrides ?? []).map(toApiGoalOverride),
		github_repo: project.githubRepo ?? null,
		category: project.category ?? null,
		autostart_repos: project.autostartRepos ?? [],
		kind: project.kind,
		contract:
			project.kind === "day_job" && project.contract ? toApiContract(project.contract) : null,
	};
}

export function toContractTerm(api: ApiContractTerm): ContractTerm {
	return {
		effectiveFrom: api.effective_from,
		scheduleType: api.schedule_type,
		fullTimeHours: api.full_time_hours ?? undefined,
		percentage: api.percentage ?? undefined,
		weeklyHours: api.weekly_hours ?? undefined,
		note: api.note ?? undefined,
	};
}

export function toApiContractTerm(term: ContractTerm): ApiContractTerm {
	return {
		effective_from: term.effectiveFrom,
		schedule_type: term.scheduleType,
		full_time_hours: term.fullTimeHours ?? null,
		percentage: term.percentage ?? null,
		weekly_hours: term.weeklyHours ?? null,
		note: term.note ?? null,
	};
}

export function toContract(api: ApiContract): Contract {
	return {
		terms: api.terms.map(toContractTerm),
		holidayCountry: api.holiday_country ?? undefined,
		holidaySubdivision: api.holiday_subdivision ?? undefined,
		openingBalanceHours: api.opening_balance_hours ?? 0,
		endedOn: api.ended_on ?? undefined,
	};
}

export function toApiContract(contract: Contract): ApiContract {
	return {
		terms: contract.terms.map(toApiContractTerm),
		holiday_country: contract.holidayCountry ?? null,
		holiday_subdivision: contract.holidaySubdivision ?? null,
		opening_balance_hours: contract.openingBalanceHours,
		ended_on: contract.endedOn ?? null,
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
