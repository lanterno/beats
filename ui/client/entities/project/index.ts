/**
 * Project Entity - public API
 * 
 * This entity represents a project in the time tracking system.
 * Following FSD conventions, this module exports:
 * - Model: types, domain logic, mappers
 * - API: data fetching hooks and functions
 * - UI: presentational components
 */

// Model layer
export type {
  Project,
  ProjectWithDuration,
  DailySummary,
  WeekHours,
} from "./model";
export { assignColor, toProject } from "./model";

// API layer
export {
  projectKeys,
  useProjects,
  useProject,
  useProjectWeeks,
  useInvalidateProjects,
  fetchProjects,
  fetchProjectWeek,
  fetchProjectTotal,
} from "./api";

// UI layer
export { LoadingSpinner } from "./ui";
