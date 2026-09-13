/**
 * ProjectSettingsDrawer — the per-project edit surface. Hosts the canonical
 * ProjectForm inside the shared Dialog primitive so it gets focus trap,
 * Escape-to-close, and bottom-sheet rendering on mobile for free.
 *
 * Work contracts: passes the project's contract so the form edits its
 * frame (region, opening balance, end date) and carries the terms through;
 * "Change contract…" hands over to the contract register on the page. A day
 * job still without a contract opens with the contract switch off — a
 * rename must not demand one — unless the page asked for the contract
 * section, as its "Add contract" does. A kind chosen away from day job says
 * under the kind field, before save, that the contract goes with it: the API
 * clears it and keeps nothing to come back to.
 *
 * At its foot, under a hairline, archive (with a confirm, then back to the
 * dashboard) or restore — the page's once-per-project action, moved here from
 * the danger zone that sat on every visit (Decision 12). The Archived chip in
 * the header keeps its own inline Restore.
 */

import { Archive, ArchiveRestore, Loader2 } from "lucide-react";
import { useId, useRef, useState } from "react";
import { useNavigate } from "react-router";
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
	type ProjectKind,
	projectWriteFromForm,
	useArchiveProject,
	useHolidayRegions,
	useProjects,
	useUnarchiveProject,
	useUpdateProject,
} from "@/entities/project";
import { describeError } from "@/shared/api";
import { Button, Dialog } from "@/shared/ui";
import { LABEL } from "./styles";

interface ProjectSettingsDrawerProps {
	project: Project;
	open: boolean;
	onClose: () => void;
	/** Which field to focus when the drawer opens — used by inline-clickable header. */
	autoFocusField?: ProjectFormAutoFocusField;
	/** Where "Change contract…" goes: the contract register on the page. */
	onChangeContract?: () => void;
}

const KIND_CHANGE_NOTICE =
	"Changing the kind deletes the contract: its terms, region and opening balance are not kept.";

export function ProjectSettingsDrawer({
	project,
	open,
	onClose,
	autoFocusField,
	onChangeContract,
}: ProjectSettingsDrawerProps) {
	const navigate = useNavigate();
	const updateProject = useUpdateProject();
	const archive = useArchiveProject();
	const unarchive = useUnarchiveProject();
	const { data: projects } = useProjects();
	const { data: githubStatus } = useGitHubStatus();
	const { data: holidayRegions } = useHolidayRegions();
	const [submitError, setSubmitError] = useState<unknown>(null);
	const [confirmingArchive, setConfirmingArchive] = useState(false);
	const archiveHeadingId = useId();
	// "Change contract…" closes the drawer and lands on the register.
	// The hand-over waits for the dialog's own focus return, which would
	// otherwise put focus back on the settings button a moment later.
	const changeContractRequested = useRef(false);
	// The confirm replaces the button that asked for it, and Cancel brings the
	// button back: focus follows each swap instead of falling to the dialog.
	const focusOnSwap = useRef(false);
	const takeFocusOnSwap = (node: HTMLButtonElement | null) => {
		if (node && focusOnSwap.current) {
			focusOnSwap.current = false;
			node.focus();
		}
	};

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
		setConfirmingArchive(false);
		onClose();
	};

	const handleChangeContract = () => {
		changeContractRequested.current = true;
		handleClose();
	};

	const handleArchive = () => {
		archive.mutate(project.id, {
			onSuccess: () => {
				toast.success("Project archived");
				handleClose();
				// The project has just left every active picker; the page it was
				// on is no place to stay.
				navigate("/app");
			},
			onError: (err) => toast.error(describeError(err, "Failed to archive project")),
		});
	};

	const handleRestore = () => {
		unarchive.mutate(project.id, {
			onSuccess: () => toast.success("Project restored"),
			onError: (err) => toast.error(describeError(err, "Failed to restore project")),
		});
	};

	const kindNotice =
		project.kind === "day_job" && project.contract
			? (kind: ProjectKind) => (kind === "day_job" ? null : KIND_CHANGE_NOTICE)
			: undefined;
	// Another tab may restore the project while the confirm is up.
	const confirming = confirmingArchive && !project.archived;

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
				kindNotice={kindNotice}
			/>

			<section aria-labelledby={archiveHeadingId} className="mt-6 pt-4 border-t border-border">
				<h3 id={archiveHeadingId} className={LABEL}>
					{project.archived ? "Archived" : "Archive"}
				</h3>
				{project.archived ? (
					<>
						<p className="mt-1.5 text-xs text-muted-foreground leading-normal">
							This project is archived. Restoring it makes it visible again in pickers, the sidebar,
							and lists. Sessions and history were preserved.
						</p>
						<Button
							type="button"
							variant="secondary"
							size="sm"
							className="mt-3"
							onClick={handleRestore}
							disabled={unarchive.isPending}
						>
							{unarchive.isPending ? (
								<Loader2 className="animate-spin" aria-hidden="true" />
							) : (
								<ArchiveRestore aria-hidden="true" />
							)}
							Restore project
						</Button>
					</>
				) : (
					<>
						<p className="mt-1.5 text-xs text-muted-foreground leading-normal">
							Archiving hides {project.name} from pickers, lists, and the sidebar. Sessions are
							preserved and you can restore the project later — there is no hard-delete by design.
						</p>
						{confirming ? (
							<div className="mt-3 flex flex-wrap items-center gap-2">
								<span className="text-xs text-foreground">
									Archive <strong>{project.name}</strong>?
								</span>
								<Button
									type="button"
									variant="destructive"
									size="sm"
									onClick={handleArchive}
									disabled={archive.isPending}
								>
									{archive.isPending ? "Archiving…" : "Archive project"}
								</Button>
								<Button
									ref={takeFocusOnSwap}
									type="button"
									variant="ghost"
									size="sm"
									onClick={() => {
										focusOnSwap.current = true;
										setConfirmingArchive(false);
									}}
								>
									Cancel
								</Button>
							</div>
						) : (
							<Button
								ref={takeFocusOnSwap}
								type="button"
								variant="secondary"
								size="sm"
								className="mt-3"
								onClick={() => {
									focusOnSwap.current = true;
									setConfirmingArchive(true);
								}}
							>
								<Archive aria-hidden="true" />
								Archive project
							</Button>
						)}
					</>
				)}
			</section>
		</Dialog>
	);
}
