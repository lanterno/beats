/**
 * ProjectSettingsDrawer — the per-project edit surface. Hosts the canonical
 * ProjectForm inside the shared Dialog primitive so it gets focus trap,
 * Escape-to-close, and bottom-sheet rendering on mobile for free.
 *
 * P1.2a: replaces the read-only ProjectDetails header (color was the only
 * editable field) with a real settings flow. P1.2b adds the Advanced
 * disclosure to ProjectForm; this drawer needs no change for that.
 */

import { toast } from "sonner";
import type { Project } from "@/entities/project";
import { ProjectForm, type ProjectFormValues, useUpdateProject } from "@/entities/project";
import { describeError } from "@/shared/api";
import { Dialog } from "@/shared/ui";

interface ProjectSettingsDrawerProps {
	project: Project;
	open: boolean;
	onClose: () => void;
	/** Which field to focus when the drawer opens — used by inline-clickable header. */
	autoFocusField?: "name" | "description" | "weeklyGoal";
}

export function ProjectSettingsDrawer({
	project,
	open,
	onClose,
	autoFocusField,
}: ProjectSettingsDrawerProps) {
	const updateProject = useUpdateProject();

	const initialValues: ProjectFormValues = {
		name: project.name,
		description: project.description ?? "",
		color: project.color,
		weeklyGoal: project.weeklyGoal != null ? String(project.weeklyGoal) : "",
		goalType: project.goalType ?? "target",
	};

	const handleSubmit = (values: ProjectFormValues) => {
		// Carry every field the UI manages — the silent-wipe guard from P1.1
		// only protects fields the entity now knows about, so we still need
		// to pass them all explicitly to updateProject.
		updateProject.mutate(
			{
				id: project.id,
				name: values.name,
				description: values.description || null,
				color: values.color,
				archived: project.archived,
				weekly_goal: values.weeklyGoal.trim() === "" ? null : Number(values.weeklyGoal),
				goal_type: values.goalType,
				github_repo: project.githubRepo ?? null,
				category: project.category ?? null,
				autostart_repos: project.autostartRepos ?? [],
			},
			{
				onSuccess: () => {
					toast.success("Project updated");
					onClose();
				},
				onError: (err) => toast.error(describeError(err, "Failed to update project")),
			},
		);
	};

	return (
		<Dialog
			open={open}
			onClose={onClose}
			title={`Edit ${project.name}`}
			description="Update the project's identity and weekly goal."
		>
			<ProjectForm
				initialValues={initialValues}
				submitting={updateProject.isPending}
				submitLabel="Save changes"
				onSubmit={handleSubmit}
				onCancel={onClose}
				autoFocusField={autoFocusField}
			/>
		</Dialog>
	);
}
