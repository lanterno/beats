/**
 * Project API layer - public API
 */

// Low-level API functions
export { fetchProjects, fetchProjectWeek, fetchProjectTotal } from "./projectApi";

// TanStack Query hooks
export {
  projectKeys,
  useProjects,
  useProject,
  useProjectWeeks,
  useInvalidateProjects,
} from "./queries";
