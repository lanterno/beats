/**
 * ProjectSettingsDrawer — the per-project edit surface. Hosts the canonical
 * ProjectForm inside the shared Dialog primitive so it gets focus trap,
 * Escape-to-close, and bottom-sheet rendering on mobile for free.
 *
 * P1.2a: replaces the read-only ProjectDetails header (color was the only
 * editable field) with a real settings flow.
 * P1.2b: passes category suggestions + GitHub connection state into the
 * form's Advanced disclosure.
 */

import { toast } from "sonner";
import { useGitHubStatus } from "@/entities/github";
import {
	extractCategories,
	type Project,
	ProjectForm,
	type ProjectFormValues,
	useProjects,
	useUpdateProject,
} from "@/entities/project";
import { describeError } from "@/shared/api";
import { Dialog } from "@/shared/ui";
import { OverrideManagementPanel } from "./OverrideManagementPanel";

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
	const { data: projects } = useProjects();
	const { data: githubStatus } = useGitHubStatus();

	const initialValues: ProjectFormValues = {
		name: project.name,
		description: project.description ?? "",
		color: project.color,
		weeklyGoal: project.weeklyGoal != null ? String(project.weeklyGoal) : "",
		goalType: project.goalType ?? "target",
		category: project.category ?? "",
		githubRepo: project.githubRepo ?? "",
		autostartRepos: project.autostartRepos ?? [],
	};

	const handleSubmit = (values: ProjectFormValues) => {
		updateProject.mutate(
			{
				id: project.id,
				name: values.name,
				description: values.description || null,
				color: values.color,
				archived: project.archived,
				weekly_goal: values.weeklyGoal.trim() === "" ? null : Number(values.weeklyGoal),
				goal_type: values.goalType,
				github_repo: values.githubRepo || null,
				category: values.category || null,
				autostart_repos: values.autostartRepos,
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
			description="Update identity, weekly goal, and integrations."
		>
			<ProjectForm
				initialValues={initialValues}
				submitting={updateProject.isPending}
				submitLabel="Save changes"
				onSubmit={handleSubmit}
				onCancel={onClose}
				autoFocusField={autoFocusField}
				categorySuggestions={extractCategories(projects)}
				githubConnected={githubStatus?.connected}
			/>

			<div className="mt-5">
				<OverrideManagementPanel project={project} />
			</div>
		</Dialog>
	);
}
