/**
 * NewProjectDialog — the create-project flow.
 *
 * P1.3 of the project-management revamp: replaces the bespoke modal that
 * collected only name + weekly_goal with the canonical ProjectForm hosted in
 * the shared Dialog primitive. Creation now configures every backend field
 * (color, goal_type, category, github_repo, autostart_repos, and on a day
 * job the contract's first term) so users don't have to discover the
 * settings drawer after creating their first project.
 */

import { useState } from "react";
import { toast } from "sonner";
import { useGitHubStatus } from "@/entities/github";
import { ApiError, describeError } from "@/shared/api";
import { Dialog } from "@/shared/ui";
import { useCreateProject, useHolidayRegions, useProjects } from "../api";
import type { Project } from "../model";
import { extractCategories, toProject } from "../model";
import { ProjectForm, type ProjectFormValues } from "./ProjectForm";
import { projectWriteFromForm } from "./projectFormWire";

interface NewProjectDialogProps {
	open: boolean;
	onClose: () => void;
	/** Called with the created project after a successful save. */
	onCreated?: (project: Project) => void;
}

/** A 422 with fields is the form's to show, beside the inputs; anything else is toasted. */
export function isInlineFormError(err: unknown): boolean {
	return err instanceof ApiError && err.isValidationError() && (err.fields?.length ?? 0) > 0;
}

export function NewProjectDialog({ open, onClose, onCreated }: NewProjectDialogProps) {
	const createProject = useCreateProject();
	const { data: projects } = useProjects();
	const { data: githubStatus } = useGitHubStatus();
	const { data: holidayRegions } = useHolidayRegions();
	const [submitError, setSubmitError] = useState<unknown>(null);

	const handleSubmit = async (values: ProjectFormValues) => {
		setSubmitError(null);
		try {
			const created = await createProject.mutateAsync({
				name: values.name,
				description: values.description || null,
				color: values.color,
				weekly_goal: values.weeklyGoal.trim() === "" ? null : Number(values.weeklyGoal),
				goal_type: values.goalType,
				category: values.category || null,
				github_repo: values.githubRepo || null,
				autostart_repos: values.autostartRepos,
				...projectWriteFromForm(values, undefined),
			});
			toast.success("Project created");
			onClose();
			onCreated?.(toProject(created));
		} catch (err) {
			setSubmitError(err);
			if (!isInlineFormError(err)) toast.error(describeError(err, "Failed to create project"));
		}
	};

	const handleClose = () => {
		setSubmitError(null);
		onClose();
	};

	// `key={String(open)}` resets ProjectForm's internal state each time the
	// dialog re-opens — same behavior as the old manual reset effect, without
	// putting the form's defaultValues call on every render.
	return (
		<Dialog
			open={open}
			onClose={handleClose}
			title="New project"
			description="Configure the project's identity, goal, and integrations."
		>
			<ProjectForm
				key={String(open)}
				submitting={createProject.isPending}
				submitLabel="Create project"
				onSubmit={handleSubmit}
				onCancel={handleClose}
				categorySuggestions={extractCategories(projects)}
				githubConnected={githubStatus?.connected}
				holidayRegions={holidayRegions}
				submitError={submitError}
			/>
		</Dialog>
	);
}
