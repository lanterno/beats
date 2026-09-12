/**
 * ProjectSettingsDrawer — the per-project edit surface. Hosts the canonical
 * ProjectForm inside the shared Dialog primitive so it gets focus trap,
 * Escape-to-close, and bottom-sheet rendering on mobile for free.
 *
 * P1.2a: replaces the read-only ProjectDetails header (color was the only
 * editable field) with a real settings flow.
 * P1.2b: passes category suggestions + GitHub connection state into the
 * form's Advanced disclosure.
 * Work contracts: passes the project's contract so the form edits its
 * frame (region, opening balance, end date) and carries the terms through;
 * "Change contract…" hands over to the history panel on the page. A day
 * job still without a contract opens with the contract switch off — a
 * rename must not demand one — unless the page asked for the contract
 * section, as its "Add contract" does.
 */

import { useRef, useState } from "react";
import { toast } from "sonner";
import { useGitHubStatus } from "@/entities/github";
import {
	contractFrameDefaults,
	extractCategories,
	isInlineFormError,
	type Project,
	ProjectForm,
	type ProjectFormAutoFocusField,
	type ProjectFormValues,
	projectWriteFromForm,
	useHolidayRegions,
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
	autoFocusField?: ProjectFormAutoFocusField;
	/** Where "Change contract…" goes: the contract history panel on the page. */
	onChangeContract?: () => void;
}

export function ProjectSettingsDrawer({
	project,
	open,
	onClose,
	autoFocusField,
	onChangeContract,
}: ProjectSettingsDrawerProps) {
	const updateProject = useUpdateProject();
	const { data: projects } = useProjects();
	const { data: githubStatus } = useGitHubStatus();
	const { data: holidayRegions } = useHolidayRegions();
	const [submitError, setSubmitError] = useState<unknown>(null);
	// "Change contract…" closes the drawer and lands on the history panel.
	// The hand-over waits for the dialog's own focus return, which would
	// otherwise put focus back on the settings button a moment later.
	const changeContractRequested = useRef(false);

	const initialValues: Partial<ProjectFormValues> = {
		name: project.name,
		description: project.description ?? "",
		color: project.color,
		weeklyGoal: project.weeklyGoal != null ? String(project.weeklyGoal) : "",
		goalType: project.goalType ?? "target",
		category: project.category ?? "",
		githubRepo: project.githubRepo ?? "",
		autostartRepos: project.autostartRepos ?? [],
		kind: project.kind,
		addContract: project.contract !== undefined || autoFocusField === "scheduleType",
		contract: contractFrameDefaults(project.contract),
	};

	const handleSubmit = (values: ProjectFormValues) => {
		setSubmitError(null);
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
				// `contract` is present only on a day job: leaving it out is what
				// makes the API clear it when the kind changes (a stale one sent
				// with another kind is a 409).
				...projectWriteFromForm(values, project.contract),
			},
			{
				onSuccess: () => {
					toast.success("Project updated");
					onClose();
				},
				onError: (err) => {
					setSubmitError(err);
					if (!isInlineFormError(err)) toast.error(describeError(err, "Failed to update project"));
				},
			},
		);
	};

	const handleClose = () => {
		setSubmitError(null);
		onClose();
	};

	const handleChangeContract = () => {
		changeContractRequested.current = true;
		handleClose();
	};

	return (
		<Dialog
			open={open}
			onClose={handleClose}
			title={`Edit ${project.name}`}
			description={
				project.kind === "day_job"
					? "Update identity, contract, and integrations."
					: "Update identity, weekly goal, and integrations."
			}
			onCloseAutoFocus={(event) => {
				if (!changeContractRequested.current) return;
				changeContractRequested.current = false;
				event.preventDefault();
				onChangeContract?.();
			}}
		>
			<ProjectForm
				initialValues={initialValues}
				submitting={updateProject.isPending}
				submitLabel="Save changes"
				onSubmit={handleSubmit}
				onCancel={handleClose}
				autoFocusField={autoFocusField}
				categorySuggestions={extractCategories(projects)}
				githubConnected={githubStatus?.connected}
				existingContract={project.contract}
				onChangeContract={onChangeContract ? handleChangeContract : undefined}
				holidayRegions={holidayRegions}
				submitError={submitError}
			/>

			<div className="mt-5">
				<OverrideManagementPanel project={project} />
			</div>
		</Dialog>
	);
}
