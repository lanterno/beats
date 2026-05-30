/**
 * NewProjectDialog — the create-project flow.
 *
 * P1.3 of the project-management revamp: replaces the bespoke modal that
 * collected only name + weekly_goal with the canonical ProjectForm hosted in
 * the shared Dialog primitive. Creation now configures every backend field
 * (color, goal_type, category, github_repo, autostart_repos) so users don't
 * have to discover the settings drawer after creating their first project.
 */

import { toast } from "sonner";
import { useGitHubStatus } from "@/entities/github";
import { describeError } from "@/shared/api";
import { Dialog } from "@/shared/ui";
import { useCreateProject, useProjects } from "../api";
import type { Project } from "../model";
import { extractCategories, toProject } from "../model";
import { ProjectForm, type ProjectFormValues } from "./ProjectForm";

interface NewProjectDialogProps {
	open: boolean;
	onClose: () => void;
	/** Called with the created project after a successful save. */
	onCreated?: (project: Project) => void;
}

export function NewProjectDialog({ open, onClose, onCreated }: NewProjectDialogProps) {
	const createProject = useCreateProject();
	const { data: projects } = useProjects();
	const { data: githubStatus } = useGitHubStatus();

	const handleSubmit = async (values: ProjectFormValues) => {
		try {
			const created = await createProject.mutateAsync({
				name: values.name,
				description: values.description || null,
				color: values.color,
				weekly_goal: values.weeklyGoal.trim() === "" ? null : Number(values.weeklyGoal),
				category: values.category || null,
				github_repo: values.githubRepo || null,
				autostart_repos: values.autostartRepos,
			});
			toast.success("Project created");
			onClose();
			onCreated?.(toProject(created));
		} catch (err) {
			toast.error(describeError(err, "Failed to create project"));
		}
	};

	// `key={String(open)}` resets ProjectForm's internal state each time the
	// dialog re-opens — same behavior as the old manual reset effect, without
	// putting the form's defaultValues call on every render.
	return (
		<Dialog
			open={open}
			onClose={onClose}
			title="New project"
			description="Configure the project's identity, goal, and integrations."
		>
			<ProjectForm
				key={String(open)}
				submitting={createProject.isPending}
				submitLabel="Create project"
				onSubmit={handleSubmit}
				onCancel={onClose}
				categorySuggestions={extractCategories(projects)}
				githubConnected={githubStatus?.connected}
			/>
		</Dialog>
	);
}
