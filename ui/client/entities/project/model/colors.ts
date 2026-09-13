/**
 * Project Color Assignment
 * Consistent color assignment based on project ID.
 *
 * Ten colours picked to sit on the sky: mid-saturation, no neon, each a
 * clear hue from its neighbours and none near the sunlight accent. The
 * count and order are load-bearing — assignColor hashes into this array,
 * so a project keeps its slot across re-picks. shared/ui/color-picker.tsx
 * carries the same list as its swatches (shared/ cannot import entities/).
 */

export const PROJECT_COLORS = [
	"#4E93E3", // Blue
	"#48B48C", // Jade
	"#D98B5F", // Terracotta
	"#DE6C78", // Rose
	"#9A7BDD", // Violet
	"#C97BC4", // Orchid
	"#46B3C7", // Teal
	"#7A8CA0", // Slate
	"#6E7FCF", // Indigo
	"#8FB04A", // Olive
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
