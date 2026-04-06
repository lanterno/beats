/**
 * Project Mappers
 * Convert between API types and domain types.
 */
import type { ApiProject } from "@/shared/api";
import type { Project } from "./types";
import { assignColor } from "./colors";

/**
 * Convert API project to domain Project
 */
export function toProject(apiProject: ApiProject): Project {
  const id = apiProject.id || "";
  return {
    id,
    name: apiProject.name,
    description: apiProject.description ?? undefined,
    color: assignColor(id),
    archived: apiProject.archived ?? false,
    estimation: apiProject.estimation ?? undefined,
    weeklyGoal: apiProject.weekly_goal ?? undefined,
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
    archived: project.archived,
    estimation: project.estimation ?? null,
    weekly_goal: project.weeklyGoal ?? null,
  };
}
