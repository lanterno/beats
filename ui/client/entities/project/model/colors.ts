/**
 * Project Color Assignment
 * Consistent color assignment based on project ID.
 */

/**
 * Color palette for projects
 */
export const PROJECT_COLORS = [
  "#5B9CF6", // Blue
  "#34D399", // Green
  "#FBBF24", // Amber
  "#F87171", // Red
  "#A78BFA", // Purple
  "#F472B6", // Pink
  "#22D3EE", // Cyan
  "#FB923C", // Orange
  "#818CF8", // Indigo
  "#A3E635", // Lime
] as const;

/**
 * Assign a consistent color to a project based on its ID
 */
export function assignColor(projectId: string): string {
  const hash = projectId.split("").reduce((acc, char) => {
    return acc + char.charCodeAt(0);
  }, 0);
  return PROJECT_COLORS[hash % PROJECT_COLORS.length];
}
