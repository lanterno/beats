/**
 * OrgProjectDialog — the organisation's fields of one of its projects:
 * name, description, colour, kind, category, repository and, on an edit,
 * archived. A member's goal, local repo paths and contract are theirs and
 * are not here. Every field is sent, so a save replaces what the
 * organisation had.
 */

import { useId, useState } from "react";
import { toast } from "sonner";
import type { OrgProject, OrgProjectInput } from "@/entities/organisation";
import { useCreateOrgProject, useUpdateOrgProject } from "@/entities/organisation";
import type { ProjectKind } from "@/entities/project";
import { apiFieldErrors, describeError } from "@/shared/api";
import { Button, ColorPicker, Dialog } from "@/shared/ui";
import { KIND_LABELS, KINDS } from "./kinds";
import { ERROR, FIELD, LABEL } from "./styles";

const DEFAULT_COLOR = "#4E93E3";

export interface OrgProjectDialogProps {
	organisationId: string;
	/** The project to edit; a new one without it. */
	project?: OrgProject;
	onClose: () => void;
}

export function OrgProjectDialog({ organisationId, project, onClose }: OrgProjectDialogProps) {
	const id = useId();
	const create = useCreateOrgProject(organisationId);
	const update = useUpdateOrgProject(organisationId);
	const [name, setName] = useState(project?.name ?? "");
	const [description, setDescription] = useState(project?.description ?? "");
	const [color, setColor] = useState(project?.color ?? DEFAULT_COLOR);
	const [kind, setKind] = useState<ProjectKind>(project?.kind ?? "side_project");
	const [category, setCategory] = useState(project?.category ?? "");
	const [githubRepo, setGithubRepo] = useState(project?.githubRepo ?? "");
	const [archived, setArchived] = useState(project?.archived ?? false);
	const [pickerOpen, setPickerOpen] = useState(false);
	const [errors, setErrors] = useState<Record<string, string>>({});
	const busy = create.isPending || update.isPending;

	const save = async () => {
		if (!name.trim()) {
			setErrors({ name: "A project needs a name." });
			return;
		}
		setErrors({});
		const input: OrgProjectInput = {
			name: name.trim(),
			description: description || undefined,
			color,
			kind,
			category: category || undefined,
			githubRepo: githubRepo || undefined,
			archived,
		};
		try {
			if (project) {
				await update.mutateAsync({ projectId: project.id, input });
				toast.success("Project saved");
			} else {
				await create.mutateAsync(input);
				toast.success("Project added");
			}
			onClose();
		} catch (err) {
			const fields = apiFieldErrors(err);
			setErrors(
				Object.keys(fields).length > 0
					? fields
					: { general: describeError(err, "The project could not be saved.") },
			);
		}
	};

	const text = (
		key: "name" | "description" | "category" | "github_repo",
		label: string,
		value: string,
		set: (v: string) => void,
		extra: Partial<React.InputHTMLAttributes<HTMLInputElement>> = {},
	) => (
		<div>
			<label htmlFor={`${id}-${key}`} className={LABEL}>
				{label}
			</label>
			<input
				id={`${id}-${key}`}
				type="text"
				value={value}
				onChange={(e) => set(e.target.value)}
				aria-invalid={errors[key] ? true : undefined}
				aria-describedby={errors[key] ? `${id}-${key}-error` : undefined}
				className={FIELD}
				{...extra}
			/>
			{errors[key] && (
				<p id={`${id}-${key}-error`} className={ERROR}>
					{errors[key]}
				</p>
			)}
		</div>
	);

	return (
		<Dialog
			open
			onClose={() => !busy && onClose()}
			title={project ? "Edit project" : "New project"}
			description="A project the organisation owns. It appears on a member's list once they are assigned."
			contentClassName="sm:w-full sm:max-w-[460px]"
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					void save();
				}}
				noValidate
				className="space-y-3"
			>
				{text("name", "Name", name, setName, { maxLength: 120, autoFocus: true })}
				{text("description", "Description", description, setDescription, {
					placeholder: "Optional",
				})}

				<div>
					<span id={`${id}-color-label`} className={LABEL}>
						Colour
					</span>
					<div className="relative inline-block">
						<button
							type="button"
							onClick={() => setPickerOpen((o) => !o)}
							aria-labelledby={`${id}-color-label`}
							aria-haspopup="dialog"
							aria-expanded={pickerOpen}
							className="inline-flex items-center gap-2 min-h-9 px-3 rounded-full bg-secondary text-sm font-bold text-foreground hover:bg-sidebar-accent transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
						>
							<span
								className="inline-block w-3 h-3 rounded-full shrink-0"
								style={{ backgroundColor: color }}
								aria-hidden="true"
							/>
							<span className="font-mono text-xs">{color.toUpperCase()}</span>
						</button>
						{pickerOpen && (
							<ColorPicker value={color} onChange={setColor} onClose={() => setPickerOpen(false)} />
						)}
					</div>
				</div>

				<fieldset className="border-0 p-0 m-0">
					<legend className={LABEL}>Kind</legend>
					<div className="flex flex-wrap gap-2">
						{KINDS.map((k) => (
							<label
								key={k}
								className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-bold cursor-pointer transition-colors ${
									kind === k
										? "bg-accent text-accent-foreground"
										: "bg-secondary text-foreground hover:bg-sidebar-accent"
								}`}
							>
								<input
									type="radio"
									name={`${id}-kind`}
									value={k}
									checked={kind === k}
									onChange={() => setKind(k)}
									className="sr-only"
								/>
								{KIND_LABELS[k]}
							</label>
						))}
					</div>
				</fieldset>

				<div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
					{text("category", "Category", category, setCategory, { placeholder: "Optional" })}
					{text("github_repo", "GitHub repository", githubRepo, setGithubRepo, {
						placeholder: "owner/repo · optional",
					})}
				</div>

				{project && (
					<label className="flex items-center gap-2 text-[13px] font-medium text-foreground">
						<input
							type="checkbox"
							checked={archived}
							onChange={(e) => setArchived(e.target.checked)}
							className="accent-accent"
						/>
						Archived — off every member's active list, its hours kept
					</label>
				)}

				{errors.general && (
					<p role="alert" className="text-sm text-destructive-ink">
						{errors.general}
					</p>
				)}

				<div className="flex justify-end gap-2.5 pt-1">
					<Button type="button" variant="secondary" size="sm" onClick={onClose} disabled={busy}>
						Cancel
					</Button>
					<Button type="submit" size="sm" disabled={busy}>
						{busy ? "Saving…" : project ? "Save" : "Add project"}
					</Button>
				</div>
			</form>
		</Dialog>
	);
}
