/**
 * Project model - public API
 */

// Types
export type {
  Project,
  ProjectWithDuration,
  DailySummary,
  WeekHours,
} from "./types";

// Color utilities
export { assignColor } from "./colors";

// Mappers
export { toProject } from "./mappers";
