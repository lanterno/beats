/**
 * ProjectForm — the canonical form for creating or editing a project.
 *
 * P1.2a skeleton: name, description, color, weekly_goal, goal_type. P1.2b
 * extends with the advanced fields (category / github_repo / autostart_repos).
 * Used by both the create dialog (P1.3) and the per-project settings drawer
 * so a project is configured the same way every time it's touched.
 *
 * Work contracts (docs/work-contracts-roadmap.md): a `kind` selector, and on
 * a day job the contract section. The section has one write path per
 * situation — on a project with no contract yet it creates the first term,
 * behind a "Set up the contract now" switch because a day job may wait for
 * its contract (the API allows it; the migration produces it) and a rename
 * must not demand one; on a day job that has one it edits the frame
 * (region, opening balance, end date) and shows the current term
 * read-only, because a term is changed in the history panel, where "fix
 * this term" and "new term from a date" are two different actions instead
 * of one ambiguous edit. A time-based day job hides the personal weekly
 * goal — the contract is the goal; an objective one keeps it (Decision 8).
 *
 * a11y: every field has a real <label htmlFor>; goal-type and kind use
 * icon+text instead of color alone (WCAG 1.4.1); ColorPicker is opened
 * from a button that names the currently-selected color; a failed save's
 * messages sit beside their inputs with aria-describedby, and a refused
 * submit moves focus to the first input at fault so the message is read.
 */

import {
	Briefcase,
	ChevronDown,
	ChevronRight,
	Handshake,
	Rocket,
	Target,
	TrendingDown,
} from "lucide-react";
import { type SyntheticEvent, useEffect, useMemo, useRef, useState } from "react";
import { formatDateOnly, todayIso } from "@/shared/lib";
import { Button, ColorPicker } from "@/shared/ui";
import type {
	Contract,
	ContractFrameValues,
	HolidayRegion,
	ProjectKind,
	TermFormValues,
} from "../model";
import {
	contractFrameDefaults,
	describeTerm,
	displayTermOn,
	isTimeBased,
	isTimeBasedOn,
	PROJECT_COLORS,
	termFormDefaults,
	validateContractFrame,
	validateTerm,
} from "../model";
import { AdvancedFields, isValidGithubRepo } from "./AdvancedFields";
import { ContractTermFields } from "./ContractTermFields";
import {
	emptyProjectFormErrors,
	hasProjectFormErrors,
	type ProjectFormErrors,
	projectFormFieldErrors,
} from "./projectFormWire";

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
 * a thin wire-shape conversion (`projectWriteFromForm` for kind + contract).
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
	kind: ProjectKind;
	/**
	 * On a day job with no contract yet: whether to create one now, from
	 * `term` and `contract`. Off, the day job is saved without one ("leave
	 * first, contract later"). Meaningless with an existing contract.
	 */
	addContract: boolean;
	/** The contract's first term. Read only when there is no contract yet. */
	term: TermFormValues;
	/** The contract's frame — region, opening balance, end date. Read on a day job. */
	contract: ContractFrameValues;
}

export type ProjectFormAutoFocusField =
	| "name"
	| "description"
	| "weeklyGoal"
	| "githubRepo"
	| "scheduleType"
	| "holidayCountry";

export interface ProjectFormProps {
	initialValues?: Partial<ProjectFormValues>;
	submitting?: boolean;
	submitLabel?: string;
	onSubmit: (values: ProjectFormValues) => void;
	onCancel?: () => void;
	/** Which field gets autofocused on mount — used by inline-clickable headers. */
	autoFocusField?: ProjectFormAutoFocusField;
	/** Existing category strings shown as datalist suggestions in Advanced. */
	categorySuggestions?: string[];
	/** Whether the user has GitHub OAuth connected — surfaces a hint in Advanced. */
	githubConnected?: boolean;
	/** Whether to open the Advanced section by default (e.g. when editing a
	 * project that already has advanced values set). */
	advancedOpenDefault?: boolean;
	/**
	 * The contract the project already has. Puts the contract section in
	 * frame-editing mode: the current term is shown read-only and the terms
	 * are carried through unchanged (see projectWriteFromForm).
	 */
	existingContract?: Contract;
	/** Where "Change contract…" goes — the history panel, where terms are edited. */
	onChangeContract?: () => void;
	/** Countries and subdivisions for the region picker; undefined while loading. */
	holidayRegions?: HolidayRegion[];
	/** The error a submit ended in, if any. A 422's fields land beside their inputs. */
	submitError?: unknown;
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
		kind: initial?.kind ?? "side_project",
		addContract: initial?.addContract ?? true,
		term: initial?.term ?? termFormDefaults(),
		contract: initial?.contract ?? contractFrameDefaults(),
	};
}

const KIND_OPTIONS: {
	value: ProjectKind;
	label: string;
	description: string;
	Icon: typeof Target;
}[] = [
	{
		value: "day_job",
		label: "Day job",
		description: "Employed — a contract says what a week owes",
		Icon: Briefcase,
	},
	{
		value: "freelance",
		label: "Freelance",
		description: "Client work, billed by the hour or the job",
		Icon: Handshake,
	},
	{
		value: "side_project",
		label: "Side project",
		description: "Yours — with a weekly goal if you want one",
		Icon: Rocket,
	},
];

const inputCls =
	"w-full rounded-md border border-input bg-background py-2 px-3 text-base text-foreground focus:outline-hidden focus:ring-2 focus:ring-accent/20 focus:border-accent/40 aria-invalid:border-destructive/60";
const labelCls = "block text-muted-foreground text-xs uppercase tracking-[0.12em] mb-1.5";
const errorCls = "mt-1 text-xs text-destructive";

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
	existingContract,
	onChangeContract,
	holidayRegions,
	submitError,
}: ProjectFormProps) {
	const [values, setValues] = useState<ProjectFormValues>(() => defaultValues(initialValues));
	const [pickerOpen, setPickerOpen] = useState(false);
	const [clientErrors, setClientErrors] = useState<ProjectFormErrors>(emptyProjectFormErrors);
	const serverErrors = useMemo(() => projectFormFieldErrors(submitError), [submitError]);
	const formRef = useRef<HTMLFormElement>(null);
	const [refusedSubmits, setRefusedSubmits] = useState(0);
	// A refused submit — by the form or by the API — moves focus to the
	// first input at fault, whose message aria-describedby then reads out;
	// the messages alone announce nothing. A message without an input (the
	// general alert) is focusable for the same reason.
	useEffect(() => {
		if (refusedSubmits === 0 && !submitError) return;
		formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"], [role="alert"]')?.focus();
	}, [refusedSubmits, submitError]);
	// A submit's own findings win over the server's from the attempt before.
	const errors: ProjectFormErrors = {
		...serverErrors,
		...Object.fromEntries(Object.entries(clientErrors).filter(([, v]) => v !== undefined)),
		term: { ...serverErrors.term, ...clientErrors.term },
		contract: { ...serverErrors.contract, ...clientErrors.contract },
		general: [...clientErrors.general, ...serverErrors.general],
	};

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
	const isDayJob = values.kind === "day_job";
	const today = todayIso();
	const currentTerm = existingContract ? displayTermOn(existingContract, today) : undefined;
	// Whether the form is describing a contract at all: the frame of the one
	// that exists, or the first term of a new one.
	const editsContract = isDayJob && (existingContract !== undefined || values.addContract);
	// The contract is the goal when it owes hours — judged by the term in
	// force today on an existing contract, or by the one being typed.
	const contractIsTimeBased = existingContract
		? isTimeBasedOn(existingContract, today)
		: values.addContract && isTimeBased(values.term.scheduleType);
	const showsPersonalGoal = !isDayJob || !contractIsTimeBased;

	const validate = (): ProjectFormErrors => {
		const next = emptyProjectFormErrors();
		if (!trimmedName) next.name = "Name is required";
		if (showsPersonalGoal && values.weeklyGoal.trim() !== "") {
			const goal = Number(values.weeklyGoal);
			if (Number.isNaN(goal) || goal < 0) {
				next.weeklyGoal = "Weekly goal must be a positive number of hours";
			}
		}
		if (!isValidGithubRepo(values.githubRepo)) {
			next.githubRepo = "GitHub repo must look like owner/repo";
		}
		if (editsContract) {
			if (!existingContract) next.term = validateTerm(values.term);
			next.contract = validateContractFrame(
				values.contract,
				existingContract ? existingContract.terms[0]?.effectiveFrom : values.term.effectiveFrom,
			);
		}
		return next;
	};

	const handleSubmit = (e: SyntheticEvent<HTMLFormElement>) => {
		e.preventDefault();
		const next = validate();
		setClientErrors(next);
		if (hasProjectFormErrors(next)) {
			if (next.githubRepo) setAdvancedOpen(true);
			setRefusedSubmits((n) => n + 1);
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
	const setFrame = <K extends keyof ContractFrameValues>(k: K, v: ContractFrameValues[K]) =>
		setValues((s) => ({ ...s, contract: { ...s.contract, [k]: v } }));

	const selectedRegion = holidayRegions?.find((r) => r.code === values.contract.holidayCountry);
	// Until the list arrives, keep whatever code the contract already has
	// selectable so a re-render cannot blank it.
	const countryOptions: HolidayRegion[] =
		holidayRegions ??
		(values.contract.holidayCountry
			? [
					{
						code: values.contract.holidayCountry,
						name: values.contract.holidayCountry,
						subdivisions: [],
					},
				]
			: []);

	return (
		<form ref={formRef} onSubmit={handleSubmit} className="space-y-4" noValidate>
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
					aria-invalid={errors.name ? true : undefined}
					aria-describedby={errors.name ? "project-form-name-error" : undefined}
					className={inputCls}
				/>
				{errors.name && (
					<p id="project-form-name-error" className={errorCls}>
						{errors.name}
					</p>
				)}
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

			{/* Kind — same icon+text radio idiom as goal type (no color-only state). */}
			<fieldset>
				<legend id="project-form-kind" className={labelCls}>
					Kind
				</legend>
				<div
					className="grid grid-cols-1 sm:grid-cols-3 gap-2"
					role="radiogroup"
					aria-labelledby="project-form-kind"
					aria-describedby={errors.kind ? "project-form-kind-error" : undefined}
				>
					{KIND_OPTIONS.map(({ value, label, description, Icon }) => {
						const selected = values.kind === value;
						return (
							<label
								key={value}
								className={`flex items-start gap-2 rounded-md border min-h-12 px-3 py-2 cursor-pointer transition-colors ${
									selected ? "border-accent/60 bg-accent/10" : "border-input hover:bg-secondary/40"
								}`}
							>
								<input
									type="radio"
									name="project-form-kind"
									value={value}
									checked={selected}
									onChange={() =>
										// Choosing a day job reveals the contract section (the
										// roadmap's rule), whatever the switch said before.
										setValues((s) => ({
											...s,
											kind: value,
											addContract: value === "day_job" ? true : s.addContract,
										}))
									}
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
				{errors.kind && (
					<p id="project-form-kind-error" className={errorCls}>
						{errors.kind}
					</p>
				)}
			</fieldset>

			{isDayJob && (
				<section
					aria-labelledby="project-form-contract"
					className="rounded-lg border border-border/60 bg-secondary/10 p-3 space-y-3"
				>
					<h3
						id="project-form-contract"
						className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground"
					>
						Contract
					</h3>

					{!existingContract && (
						<label className="flex items-start gap-2 text-sm text-foreground cursor-pointer">
							<input
								type="checkbox"
								checked={values.addContract}
								onChange={(e) => set("addContract", e.target.checked)}
								aria-describedby="project-form-add-contract-hint"
								className="mt-1 shrink-0"
							/>
							<span>
								Set up the contract now
								<span
									id="project-form-add-contract-hint"
									className="block text-[11px] text-muted-foreground/70"
								>
									A day job can wait for its contract — add it later from the project page.
								</span>
							</span>
						</label>
					)}

					{existingContract && currentTerm ? (
						<div className="rounded-md bg-background/40 px-3 py-2 text-sm">
							<p className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
								Current term
							</p>
							<p className="text-foreground mt-0.5">
								{describeTerm(currentTerm)}
								<span className="text-muted-foreground">
									{" "}
									· since {formatDateOnly(currentTerm.effectiveFrom)}
								</span>
							</p>
							{onChangeContract && (
								<Button
									type="button"
									variant="link"
									size="sm"
									onClick={onChangeContract}
									className="px-0 h-auto mt-1 text-xs"
								>
									Change contract…
								</Button>
							)}
							<p className="text-[11px] text-muted-foreground/70 mt-1">
								Terms — a new percentage, a start date — are edited in the contract history.
							</p>
						</div>
					) : (
						values.addContract && (
							<ContractTermFields
								values={values.term}
								onChange={(term) => set("term", term)}
								errors={errors.term}
								autoFocusField={autoFocusField === "scheduleType" ? "scheduleType" : undefined}
							/>
						)
					)}

					{editsContract && (
						<>
							<div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
								<div>
									<label htmlFor="project-form-holiday-country" className={labelCls}>
										Holiday region
									</label>
									<select
										id="project-form-holiday-country"
										value={values.contract.holidayCountry}
										onChange={(e) =>
											setValues((s) => ({
												...s,
												contract: {
													...s.contract,
													holidayCountry: e.target.value,
													holidaySubdivision: "",
												},
											}))
										}
										autoFocus={autoFocusField === "holidayCountry"}
										aria-invalid={errors.contract.holidayCountry ? true : undefined}
										aria-describedby={
											errors.contract.holidayCountry
												? "project-form-holiday-country-error"
												: undefined
										}
										className={inputCls}
									>
										<option value="">
											{holidayRegions ? "No region — holidays not counted" : "Loading regions…"}
										</option>
										{countryOptions.map((r) => (
											<option key={r.code} value={r.code}>
												{r.name}
											</option>
										))}
									</select>
									{errors.contract.holidayCountry && (
										<p id="project-form-holiday-country-error" className={errorCls}>
											{errors.contract.holidayCountry}
										</p>
									)}
								</div>
								{selectedRegion && selectedRegion.subdivisions.length > 0 && (
									<div>
										<label htmlFor="project-form-holiday-subdivision" className={labelCls}>
											Region within {selectedRegion.name}
										</label>
										<select
											id="project-form-holiday-subdivision"
											value={values.contract.holidaySubdivision}
											onChange={(e) => setFrame("holidaySubdivision", e.target.value)}
											aria-invalid={errors.contract.holidaySubdivision ? true : undefined}
											aria-describedby={
												errors.contract.holidaySubdivision
													? "project-form-holiday-subdivision-error"
													: undefined
											}
											className={inputCls}
										>
											<option value="">Whole country</option>
											{selectedRegion.subdivisions.map((sd) => (
												<option key={sd.code} value={sd.code}>
													{sd.name}
												</option>
											))}
										</select>
										{errors.contract.holidaySubdivision && (
											<p id="project-form-holiday-subdivision-error" className={errorCls}>
												{errors.contract.holidaySubdivision}
											</p>
										)}
									</div>
								)}
							</div>

							<div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
								<div>
									<label htmlFor="project-form-opening-balance" className={labelCls}>
										Opening balance (hours)
									</label>
									<input
										id="project-form-opening-balance"
										type="number"
										step="0.25"
										inputMode="decimal"
										value={values.contract.openingBalanceHours}
										onChange={(e) => setFrame("openingBalanceHours", e.target.value)}
										placeholder="0"
										aria-invalid={errors.contract.openingBalanceHours ? true : undefined}
										aria-describedby={
											errors.contract.openingBalanceHours
												? "project-form-opening-balance-error"
												: "project-form-opening-balance-hint"
										}
										className={inputCls}
									/>
									{errors.contract.openingBalanceHours ? (
										<p id="project-form-opening-balance-error" className={errorCls}>
											{errors.contract.openingBalanceHours}
										</p>
									) : (
										<p
											id="project-form-opening-balance-hint"
											className="mt-1 text-[11px] text-muted-foreground/70"
										>
											Hours banked before Beats started counting; negative if owed.
										</p>
									)}
								</div>
								{existingContract && (
									<div>
										<label htmlFor="project-form-ended-on" className={labelCls}>
											Ended on (optional)
										</label>
										<input
											id="project-form-ended-on"
											type="date"
											value={values.contract.endedOn}
											onChange={(e) => setFrame("endedOn", e.target.value)}
											aria-invalid={errors.contract.endedOn ? true : undefined}
											aria-describedby={
												errors.contract.endedOn ? "project-form-ended-on-error" : undefined
											}
											className={inputCls}
										/>
										{errors.contract.endedOn && (
											<p id="project-form-ended-on-error" className={errorCls}>
												{errors.contract.endedOn}
											</p>
										)}
									</div>
								)}
							</div>
						</>
					)}
				</section>
			)}

			{showsPersonalGoal && (
				<>
					<div>
						<label htmlFor="project-form-weekly-goal" className={labelCls}>
							{isDayJob
								? "Personal weekly goal (hours, optional)"
								: "Weekly goal (hours, optional)"}
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
							aria-invalid={errors.weeklyGoal ? true : undefined}
							aria-describedby={errors.weeklyGoal ? "project-form-weekly-goal-error" : undefined}
							className={inputCls}
						/>
						{errors.weeklyGoal && (
							<p id="project-form-weekly-goal-error" className={errorCls}>
								{errors.weeklyGoal}
							</p>
						)}
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
											selected
												? "border-accent/60 bg-accent/10"
												: "border-input hover:bg-secondary/40"
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
				</>
			)}

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
							errors={{
								category: errors.category,
								githubRepo: errors.githubRepo,
								autostartRepos: errors.autostartRepos,
							}}
						/>
					</div>
				)}
			</div>

			{errors.general.length > 0 && (
				<div className="text-sm text-destructive space-y-0.5" role="alert" tabIndex={-1}>
					{errors.general.map((message) => (
						<p key={message}>{message}</p>
					))}
				</div>
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
