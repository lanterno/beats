/**
 * ProjectForm — the canonical form for creating or editing a project.
 *
 * P1.2a skeleton: name, description, color, weekly_goal, goal_type. P1.2b
 * extends with the advanced fields (category / github_repo / autostart_repos).
 * Used by both the create dialog (P1.3) and the per-project settings drawer
 * so a project is configured the same way every time it's touched.
 *
 * a11y: every field has a real <label htmlFor>; goal-type uses icon+text
 * (Target / Cap) instead of color alone (WCAG 1.4.1); ColorPicker is opened
 * from a button that names the currently-selected color.
 */

import { ChevronDown, ChevronRight, Target, TrendingDown } from "lucide-react";
import { useState } from "react";
import { Button, ColorPicker } from "@/shared/ui";
import { PROJECT_COLORS } from "../model";
import { AdvancedFields, isValidGithubRepo } from "./AdvancedFields";

// FF.11: rotate the default color through PROJECT_COLORS per ProjectForm
// mount so consecutive new projects don't all open with the same #5B9CF6
// seed (the pre-FF.11 `assignColor("new")` always hashed to index 0).
// Module-level counter is intentional — deterministic per session, no
// plumbing required from consumers, and the user can still override via
// the ColorPicker before submit.
let nextDefaultColorIndex = 0;
function pickDefaultProjectColor(): string {
	const color = PROJECT_COLORS[nextDefaultColorIndex % PROJECT_COLORS.length];
	nextDefaultColorIndex += 1;
	return color;
}

/**
 * Field set captured by the form. Aligns with the domain Project shape so
 * callers can pass it straight through to createProject/updateProject after
 * a thin wire-shape conversion.
 */
export interface ProjectFormValues {
	name: string;
	description: string;
	color: string;
	weeklyGoal: string; // empty string = "no goal"; parsed to number on submit
	goalType: "target" | "cap";
	category: string;
	githubRepo: string;
	autostartRepos: string[];
}

export interface ProjectFormProps {
	initialValues?: Partial<ProjectFormValues>;
	submitting?: boolean;
	submitLabel?: string;
	onSubmit: (values: ProjectFormValues) => void;
	onCancel?: () => void;
	/** Which field gets autofocused on mount — used by inline-clickable headers. */
	autoFocusField?: "name" | "description" | "weeklyGoal" | "githubRepo";
	/** Existing category strings shown as datalist suggestions in Advanced. */
	categorySuggestions?: string[];
	/** Whether the user has GitHub OAuth connected — surfaces a hint in Advanced. */
	githubConnected?: boolean;
	/** Whether to open the Advanced section by default (e.g. when editing a
	 * project that already has advanced values set). */
	advancedOpenDefault?: boolean;
}

function defaultValues(initial?: Partial<ProjectFormValues>): ProjectFormValues {
	return {
		name: initial?.name ?? "",
		description: initial?.description ?? "",
		color: initial?.color ?? pickDefaultProjectColor(),
		weeklyGoal: initial?.weeklyGoal ?? "",
		goalType: initial?.goalType ?? "target",
		category: initial?.category ?? "",
		githubRepo: initial?.githubRepo ?? "",
		autostartRepos: initial?.autostartRepos ?? [],
	};
}

export function ProjectForm({
	initialValues,
	submitting,
	submitLabel = "Save",
	onSubmit,
	onCancel,
	autoFocusField = "name",
	categorySuggestions,
	githubConnected,
	advancedOpenDefault,
}: ProjectFormProps) {
	const [values, setValues] = useState<ProjectFormValues>(() => defaultValues(initialValues));
	const [pickerOpen, setPickerOpen] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const hasAdvancedValues =
		(initialValues?.category && initialValues.category.trim() !== "") ||
		(initialValues?.githubRepo && initialValues.githubRepo.trim() !== "") ||
		(initialValues?.autostartRepos && initialValues.autostartRepos.length > 0);
	// Forcing Advanced open when an advanced field is the autofocus target —
	// otherwise the autoFocus prop targets an unmounted input and the drawer
	// opens with no visible focus signal.
	const advancedFocusRequested = autoFocusField === "githubRepo";
	const [advancedOpen, setAdvancedOpen] = useState(
		advancedOpenDefault ?? (Boolean(hasAdvancedValues) || advancedFocusRequested),
	);

	const trimmedName = values.name.trim();

	const handleSubmit = (e: React.FormEvent) => {
		e.preventDefault();
		setError(null);

		if (!trimmedName) {
			setError("Name is required");
			return;
		}
		if (values.weeklyGoal.trim() !== "") {
			const goal = Number(values.weeklyGoal);
			if (Number.isNaN(goal) || goal < 0) {
				setError("Weekly goal must be a positive number of hours");
				return;
			}
		}
		if (!isValidGithubRepo(values.githubRepo)) {
			setError("GitHub repo must look like owner/repo");
			setAdvancedOpen(true);
			return;
		}

		// Trim string fields and drop blank autostart paths before submit.
		onSubmit({
			...values,
			name: trimmedName,
			description: values.description.trim(),
			category: values.category.trim(),
			githubRepo: values.githubRepo.trim(),
			autostartRepos: values.autostartRepos.map((r) => r.trim()).filter((r) => r !== ""),
		});
	};

	const set = <K extends keyof ProjectFormValues>(k: K, v: ProjectFormValues[K]) =>
		setValues((s) => ({ ...s, [k]: v }));

	const inputCls =
		"w-full rounded-md border border-input bg-background py-2 px-3 text-base text-foreground focus:outline-hidden focus:ring-2 focus:ring-accent/20 focus:border-accent/40";
	const labelCls = "block text-muted-foreground text-xs uppercase tracking-[0.12em] mb-1.5";

	return (
		<form onSubmit={handleSubmit} className="space-y-4">
			<div>
				<label htmlFor="project-form-name" className={labelCls}>
					Name
				</label>
				<input
					id="project-form-name"
					value={values.name}
					onChange={(e) => set("name", e.target.value)}
					required
					autoFocus={autoFocusField === "name"}
					placeholder="e.g. Deep Work"
					className={inputCls}
				/>
			</div>

			<div>
				<label htmlFor="project-form-description" className={labelCls}>
					Description (optional)
				</label>
				<input
					id="project-form-description"
					value={values.description}
					onChange={(e) => set("description", e.target.value)}
					autoFocus={autoFocusField === "description"}
					placeholder="What this project covers"
					className={inputCls}
				/>
			</div>

			<div>
				<span id="project-form-color-label" className={labelCls}>
					Color
				</span>
				<div className="relative inline-block">
					<button
						type="button"
						onClick={() => setPickerOpen((o) => !o)}
						aria-labelledby="project-form-color-label"
						aria-haspopup="dialog"
						aria-expanded={pickerOpen}
						className="inline-flex items-center gap-2 min-h-9 px-3 rounded-md border border-input bg-background text-sm text-foreground hover:bg-secondary/40 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
					>
						<span
							className="inline-block w-3 h-3 rounded-full shrink-0"
							style={{ backgroundColor: values.color }}
							aria-hidden="true"
						/>
						<span className="font-mono text-xs tabular-nums">{values.color.toUpperCase()}</span>
					</button>
					{pickerOpen && (
						<ColorPicker
							value={values.color}
							onChange={(c) => set("color", c)}
							onClose={() => setPickerOpen(false)}
						/>
					)}
				</div>
			</div>

			<div>
				<label htmlFor="project-form-weekly-goal" className={labelCls}>
					Weekly goal (hours, optional)
				</label>
				<input
					id="project-form-weekly-goal"
					type="number"
					min="0"
					step="0.5"
					value={values.weeklyGoal}
					onChange={(e) => set("weeklyGoal", e.target.value)}
					autoFocus={autoFocusField === "weeklyGoal"}
					placeholder="e.g. 10"
					className={inputCls}
				/>
			</div>

			{/* Goal type — radio with icon + text per a11y principle (no color-only state). */}
			<fieldset>
				<legend id="project-form-goal-type" className={labelCls}>
					Goal type
				</legend>
				<div className="flex gap-2" role="radiogroup" aria-labelledby="project-form-goal-type">
					{[
						{
							value: "target" as const,
							label: "Target",
							description: "Hit at least this many hours",
							Icon: Target,
						},
						{
							value: "cap" as const,
							label: "Cap",
							description: "Stay under this many hours",
							Icon: TrendingDown,
						},
					].map(({ value, label, description, Icon }) => {
						const selected = values.goalType === value;
						return (
							<label
								key={value}
								className={`flex-1 flex items-start gap-2 rounded-md border min-h-12 px-3 py-2 cursor-pointer transition-colors ${
									selected ? "border-accent/60 bg-accent/10" : "border-input hover:bg-secondary/40"
								}`}
							>
								<input
									type="radio"
									name="project-form-goal-type"
									value={value}
									checked={selected}
									onChange={() => set("goalType", value)}
									className="mt-1 shrink-0"
								/>
								<div className="flex-1 min-w-0">
									<div className="flex items-center gap-1.5 text-sm font-medium text-foreground">
										<Icon className="w-3.5 h-3.5" aria-hidden="true" />
										{label}
									</div>
									<p className="text-[11px] text-muted-foreground mt-0.5">{description}</p>
								</div>
							</label>
						);
					})}
				</div>
			</fieldset>

			{/* Advanced disclosure — category, GitHub repo, autostart paths.
			    Opens by default when editing a project that already has
			    advanced values, so the user sees what they already set. */}
			<div className="pt-1 border-t border-border/40">
				<button
					type="button"
					onClick={() => setAdvancedOpen((o) => !o)}
					aria-expanded={advancedOpen}
					aria-controls="project-form-advanced"
					className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 rounded mt-2"
				>
					{advancedOpen ? (
						<ChevronDown className="w-3.5 h-3.5" />
					) : (
						<ChevronRight className="w-3.5 h-3.5" />
					)}
					Advanced
				</button>
				{advancedOpen && (
					<div id="project-form-advanced" className="mt-3">
						<AdvancedFields
							values={{
								category: values.category,
								githubRepo: values.githubRepo,
								autostartRepos: values.autostartRepos,
							}}
							onChange={(next) =>
								setValues((s) => ({
									...s,
									category: next.category,
									githubRepo: next.githubRepo,
									autostartRepos: next.autostartRepos,
								}))
							}
							categorySuggestions={categorySuggestions}
							githubConnected={githubConnected}
							autoFocusField={autoFocusField === "githubRepo" ? "githubRepo" : undefined}
						/>
					</div>
				)}
			</div>

			{error && (
				<p className="text-sm text-destructive" role="alert">
					{error}
				</p>
			)}

			<div className="flex gap-2 pt-1">
				<Button type="submit" disabled={!trimmedName || submitting} className="flex-1">
					{submitting ? "Saving…" : submitLabel}
				</Button>
				{onCancel && (
					<Button type="button" variant="outline" onClick={onCancel}>
						Cancel
					</Button>
				)}
			</div>
		</form>
	);
}
