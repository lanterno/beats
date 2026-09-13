/**
 * ContractRegister — the rail's first panel (docs/project-page-roadmap.md,
 * "The page", Rail). On a day job with a contract it is the register: the
 * term in force and the next one, the terms as a step chart over the
 * contract's life, the full list with edit and remove, "+ Change contract
 * from…", and the constants (region, what was brought forward, the end).
 * On any other kind — or a day job still without a contract that has a
 * personal goal — it is the Goal: the goal in force, its dated history as the
 * same chart, and the override list with remove.
 *
 * Terms are edited here and not in the settings form, so a percentage change
 * is never ambiguous between "fix the current term" and "a new term from this
 * date" — they are two buttons. Every change PUTs the whole contract; the
 * last remaining term cannot be removed, since a contract needs one.
 */

import { Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { type Ref, useId, useRef, useState } from "react";
import { toast } from "sonner";
import type {
	Contract,
	ContractTerm,
	GoalOverride,
	ProjectFormAutoFocusField,
	ProjectWithDuration,
	TermFieldErrors,
	TermFormValues,
} from "@/entities/project";
import {
	ContractTermFields,
	contractFieldErrors,
	describeTerm,
	formatSignedHours,
	permanentOverrideOn,
	sortTerms,
	standingGoalOn,
	termFormDefaults,
	termFromForm,
	termHoursPerWeek,
	termOn,
	toApiContract,
	toPercent,
	useHolidayRegions,
	useUpdateContract,
	useUpdateGoalOverrides,
	validateTerm,
	weekNumber,
} from "@/entities/project";
import { apiFieldErrors, describeError } from "@/shared/api";
import { cn, mondayOfIso } from "@/shared/lib";
import { Button, Dialog, Panel } from "@/shared/ui";
import { longDate, plainDate } from "./dates";
import { type ChartStep, stepChartGeometry } from "./stepChart";
import { LABEL, LINKISH } from "./styles";

export interface ContractRegisterProps {
	project: ProjectWithDuration;
	todayIso: string;
	/** The local day of the project's first session — where a goal's first step starts. */
	firstTrackedIso?: string;
	/** Opens the settings drawer on a field. */
	onOpenSettings: (field: ProjectFormAutoFocusField) => void;
	/** "+ Change contract from…", so the settings form can hand focus here. */
	changeButtonRef?: Ref<HTMLButtonElement>;
}

/** `.reg .inforce .big2` — the term in force, in the display face. */
const BIG2 = "font-heading text-xl font-extrabold tracking-[-0.01em] text-foreground";
const STATUS =
	"font-body text-[9.5px] font-bold tracking-[0.1em] uppercase px-[9px] py-0.5 rounded-full whitespace-nowrap";
const OP =
	"grid place-items-center w-[22px] h-[22px] rounded-full text-muted-foreground hover:bg-sidebar-accent hover:text-foreground transition-colors disabled:opacity-40 disabled:pointer-events-none focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";
/** Edit and remove: hidden until the row is hovered or focused, where there is hover at all. */
const OPS =
	"inline-flex gap-0.5 [@media(hover:hover)]:opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity";
const ROW =
	"group grid grid-cols-[minmax(0,1fr)_auto] [grid-template-areas:'from_st'_'what_what'_'note_note'] gap-x-2 gap-y-0.5 items-center py-[9px] border-t border-border text-[12.5px]";
const CONST_BUTTON =
	"text-accent-ink ml-1.5 font-bold hover:underline underline-offset-[3px] rounded focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

function hoursLabel(hours: number): string {
	return `${Math.round(hours * 100) / 100} h`;
}

/** "Part time · 80% of 42 h", "Full time · 42 h", "Custom · 32 h", "Objective". */
function termHeadline(term: ContractTerm): string {
	const weekly = termHoursPerWeek(term);
	switch (term.scheduleType) {
		case "part_time":
			return term.fullTimeHours != null && term.percentage != null
				? `Part time · ${toPercent(term.percentage)}% of ${hoursLabel(term.fullTimeHours)}`
				: "Part time";
		case "full_time":
			return weekly == null ? "Full time" : `Full time · ${hoursLabel(weekly)}`;
		case "custom":
			return weekly == null ? "Custom" : `Custom · ${hoursLabel(weekly)}`;
		case "objective":
			return "Objective";
	}
}

/** Under a step's line: "80% · 33.6 h", "100% · 42 h", "32 h", "objective". */
function termChartLabel(term: ContractTerm): string {
	const weekly = termHoursPerWeek(term);
	if (weekly == null) return "objective";
	if (term.percentage != null && term.scheduleType !== "custom") {
		return `${toPercent(term.percentage)}% · ${hoursLabel(weekly)}`;
	}
	return hoursLabel(weekly);
}

/** "+2.0 h", "0.0 h" where the chip would say "even". */
function signed(hours: number): string {
	const text = formatSignedHours(hours);
	return text === "even" ? "0.0 h" : text;
}

function StepChart({
	steps,
	todayIso,
	endedOn,
	label,
}: {
	steps: ChartStep[];
	todayIso: string;
	endedOn?: string;
	label: string;
}) {
	// useId's colons would end the fragment in `url(#…)`.
	const gradient = `meadow-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
	const chart = stepChartGeometry({ steps, todayIso, endedOn });
	if (!chart) return null;
	const path = (kind: "solid" | "dashed") =>
		chart.segments
			.filter((s) => s.kind === kind)
			.map((s) => `M${s.x1},${s.y1}L${s.x2},${s.y2}`)
			.join("");
	const solid = path("solid");
	const dashed = path("dashed");
	return (
		<svg
			viewBox={`0 0 ${chart.width} ${chart.height}`}
			role="img"
			aria-label={label}
			className="mt-3.5 w-full max-w-[26rem] h-auto block overflow-visible font-mono text-[9.5px] font-bold [&_text]:[paint-order:stroke] [&_text]:stroke-card [&_text]:[stroke-width:3px] [&_text]:[stroke-linejoin:round]"
		>
			<defs>
				<linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
					<stop offset="0" style={{ stopColor: "var(--hill-mid)", stopOpacity: 0.6 }} />
					<stop offset="1" style={{ stopColor: "var(--hill-mid)", stopOpacity: 0.06 }} />
				</linearGradient>
			</defs>
			{chart.grid.map((gy) => (
				<line
					key={gy}
					x1={4}
					x2={chart.width - 4}
					y1={gy}
					y2={gy}
					className="stroke-border"
					strokeWidth={1}
				/>
			))}
			{chart.areas.map((d) => (
				<path key={d} d={d} fill={`url(#${gradient})`} />
			))}
			{solid && (
				<path
					d={solid}
					fill="none"
					className="stroke-success"
					strokeWidth={2.5}
					strokeLinejoin="round"
					strokeLinecap="round"
				/>
			)}
			{dashed && (
				<path
					d={dashed}
					fill="none"
					className="stroke-muted-foreground"
					strokeWidth={1.5}
					strokeDasharray="3 4"
					strokeLinecap="round"
				/>
			)}
			{chart.today && (
				<>
					<line
						x1={chart.today.x}
						x2={chart.today.x}
						y1={chart.today.top - 3}
						y2={chart.baseline}
						className="stroke-accent"
						strokeWidth={2}
						strokeLinecap="round"
					/>
					<text
						x={chart.today.x}
						y={chart.today.top - 7}
						textAnchor="middle"
						className="fill-muted-foreground"
					>
						today
					</text>
				</>
			)}
			{chart.labels.map((t) => (
				<text key={`l-${t.x}-${t.text}`} x={t.x} y={t.y} className="fill-foreground">
					{t.text}
				</text>
			))}
			{chart.axis.map((t) => (
				<text
					key={`a-${t.x}-${t.text}`}
					x={t.x}
					y={t.y}
					textAnchor={t.anchor}
					className="fill-muted-foreground"
				>
					{t.text}
				</text>
			))}
		</svg>
	);
}

/** "IN FORCE" in leaf, "PLANNED" in the neutral ghost. */
function StatusPill({ status }: { status: "in-force" | "planned" }) {
	return status === "planned" ? (
		<span className={cn(STATUS, "bg-tint-other text-tint-other-ink")}>Planned</span>
	) : (
		<span className={cn(STATUS, "bg-tint-holiday text-tint-holiday-ink")}>In force</span>
	);
}

/** The goal an override sets: "8 h / week · target", "No goal that week". */
function overrideGoal(o: GoalOverride, fallbackType: "target" | "cap"): string {
	if (o.weeklyGoal == null) return o.weekOf ? "No goal that week" : "No goal";
	return `${hoursLabel(o.weeklyGoal)} / week · ${o.goalType ?? fallbackType}`;
}

/**
 * Every goal override, oldest first, with remove. An override is removed by
 * identity — two stored for the same Monday (a legacy case) must not both go
 * when one is clicked.
 */
function OverrideList({ project, todayIso }: { project: ProjectWithDuration; todayIso: string }) {
	const updateOverrides = useUpdateGoalOverrides();
	const [pendingIndex, setPendingIndex] = useState<number | null>(null);
	const overrides = project.goalOverrides ?? [];
	if (overrides.length === 0) return null;

	const monday = mondayOfIso(todayIso);
	const inForce = permanentOverrideOn(overrides, monday);
	const fallbackType = project.goalType ?? "target";
	const sorted = [...overrides].sort((a, b) =>
		(a.weekOf ?? a.effectiveFrom ?? "").localeCompare(b.weekOf ?? b.effectiveFrom ?? ""),
	);

	const handleRemove = (target: GoalOverride) => {
		const sourceIndex = overrides.indexOf(target);
		if (sourceIndex === -1) return;
		setPendingIndex(sourceIndex);
		updateOverrides.mutate(
			{
				projectId: project.id,
				overrides: overrides
					.filter((_, i) => i !== sourceIndex)
					.map((o) => ({
						week_of: o.weekOf ?? null,
						effective_from: o.effectiveFrom ?? null,
						weekly_goal: o.weeklyGoal,
						goal_type: o.goalType ?? null,
						note: o.note ?? null,
					})),
			},
			{
				onSuccess: () => toast.success("Override removed"),
				onError: (err) => toast.error(describeError(err, "Failed to remove override")),
				onSettled: () => setPendingIndex(null),
			},
		);
	};

	return (
		<ul className="mt-3 flex flex-col" aria-label="Goal overrides">
			{sorted.map((o) => {
				const sourceIndex = overrides.indexOf(o);
				const date = o.weekOf ?? o.effectiveFrom ?? "";
				const from = o.weekOf
					? `${weekNumber(o.weekOf)} · ${plainDate(o.weekOf)}`
					: `From ${plainDate(date)}`;
				const status =
					o === inForce
						? "in-force"
						: o.effectiveFrom && o.effectiveFrom > monday
							? "planned"
							: null;
				const note = [o.weekOf ? "one-week override" : null, o.note ? `“${o.note}”` : null]
					.filter((part): part is string => part !== null)
					.join(" · ");
				return (
					<li key={`${o.weekOf ?? ""}::${o.effectiveFrom ?? ""}::${sourceIndex}`} className={ROW}>
						<span className="[grid-area:from] text-[11.5px] text-muted-foreground whitespace-nowrap font-bold font-mono">
							{from}
						</span>
						<span className="[grid-area:st] inline-flex gap-1.5 items-center justify-self-end">
							{status && <StatusPill status={status} />}
							<span className={OPS}>
								<button
									type="button"
									onClick={() => handleRemove(o)}
									disabled={pendingIndex !== null}
									aria-label={`Remove override for ${plainDate(date)}`}
									className={cn(OP, "hover:text-destructive")}
								>
									{pendingIndex === sourceIndex ? (
										<Loader2 className="w-[11px] h-[11px] animate-spin" aria-hidden="true" />
									) : (
										<Trash2 className="w-[11px] h-[11px]" aria-hidden="true" />
									)}
								</button>
							</span>
						</span>
						<span className="[grid-area:what] min-w-0 text-foreground font-medium">
							{overrideGoal(o, fallbackType)}
						</span>
						{note && (
							<span className="[grid-area:note] text-xs text-muted-foreground truncate">
								{note}
							</span>
						)}
					</li>
				);
			})}
		</ul>
	);
}

type Editor = { mode: "add" } | { mode: "edit"; index: number };

function ContractVariant({
	project,
	contract,
	todayIso,
	onOpenSettings,
	changeButtonRef,
}: {
	project: ProjectWithDuration;
	contract: Contract;
	todayIso: string;
	onOpenSettings: (field: ProjectFormAutoFocusField) => void;
	changeButtonRef?: Ref<HTMLButtonElement>;
}) {
	const updateContract = useUpdateContract();
	const { data: regions } = useHolidayRegions();
	const [editor, setEditor] = useState<Editor | null>(null);
	const [pendingIndex, setPendingIndex] = useState<number | null>(null);
	// "+ Change contract from…" is the page's too (the settings form hands focus
	// to it), and it takes focus when a term dialog closes on a re-dated row
	// whose Edit button is gone.
	const changeButton = useRef<HTMLButtonElement | null>(null);
	const setChangeButton = (node: HTMLButtonElement | null) => {
		changeButton.current = node;
		if (typeof changeButtonRef === "function") changeButtonRef(node);
		else if (changeButtonRef) changeButtonRef.current = node;
	};

	const terms = sortTerms(contract.terms);
	const endedOn = contract.endedOn;
	const ended = endedOn !== undefined && endedOn <= todayIso;
	const current = termOn(contract, todayIso);
	const inForce = ended ? undefined : current;
	// The headline: the term in force, the last one before the end, or the first still to come.
	const shown = current ?? terms[0];
	const next = ended
		? undefined
		: terms.find((t) => t.effectiveFrom > todayIso && (!endedOn || t.effectiveFrom <= endedOn));
	const anyPending = updateContract.isPending;

	const handleRemove = (index: number) => {
		if (terms.length <= 1) return;
		setPendingIndex(index);
		const nextContract: Contract = { ...contract, terms: terms.filter((_, i) => i !== index) };
		updateContract.mutate(
			{ projectId: project.id, contract: toApiContract(nextContract) },
			{
				onSuccess: () => toast.success("Term removed"),
				// A remove has no inputs to pin a 422 to; the message is the toast.
				onError: (err) => toast.error(describeError(err, "Failed to remove term")),
				onSettled: () => setPendingIndex(null),
			},
		);
	};

	const editing = editor?.mode === "edit" ? terms[editor.index] : undefined;
	const otherDates = terms.filter((t) => t !== editing).map((t) => t.effectiveFrom);

	const weekly = shown ? termHoursPerWeek(shown) : null;
	const sub = shown
		? `${weekly == null ? "no weekly expectation" : `${hoursLabel(weekly)}/week`} · ${
				shown.effectiveFrom > todayIso ? "from" : "since"
			} ${longDate(shown.effectiveFrom)}`
		: null;

	const steps: ChartStep[] = terms.map((t) => ({
		date: t.effectiveFrom,
		hours: termHoursPerWeek(t),
		label: termChartLabel(t),
	}));
	const chartLabel = `Hours per week over the contract's life: ${terms
		.map((t) => {
			const h = termHoursPerWeek(t);
			const planned = t.effectiveFrom > todayIso ? ", planned" : "";
			return `${h == null ? "no weekly expectation" : hoursLabel(h)} from ${plainDate(t.effectiveFrom)}${planned}`;
		})
		.join("; ")}${endedOn ? `; ${ended ? "ended" : "ends"} ${plainDate(endedOn)}` : ""}`;

	const country = regions?.find((r) => r.code === contract.holidayCountry);
	const subdivision = country?.subdivisions.find((s) => s.code === contract.holidaySubdivision);
	const constants = [
		contract.holidayCountry
			? `Holidays ${country?.name ?? contract.holidayCountry}${
					contract.holidaySubdivision
						? ` · ${subdivision?.name ?? contract.holidaySubdivision}`
						: ""
				}`
			: null,
		`Brought forward ${signed(contract.openingBalanceHours)}`,
		endedOn ? `${ended ? "Ended" : "Ends"} ${plainDate(endedOn)}` : "Ended —",
	]
		.filter((part): part is string => part !== null)
		.join(" · ");

	return (
		<Panel role="region" aria-label="Contract" padding="px-6 py-[22px]">
			<h3 className={LABEL}>Contract</h3>
			{shown && (
				<div className="mt-3">
					<p className={BIG2}>{termHeadline(shown)}</p>
					{sub && <p className="text-[12.5px] text-muted-foreground mt-0.5 font-medium">{sub}</p>}
				</div>
			)}
			{next && (
				<p className="mt-2 text-[13px] text-tint-holiday-ink font-bold leading-[1.45]">
					<span className="text-muted-foreground font-medium">Next</span> → {describeTerm(next)}{" "}
					from {longDate(next.effectiveFrom)}
				</p>
			)}
			{(terms.length >= 2 || endedOn) && (
				<StepChart steps={steps} todayIso={todayIso} endedOn={endedOn} label={chartLabel} />
			)}

			<ul className="mt-3 flex flex-col" aria-label="Terms">
				{terms.map((term, index) => {
					const when = plainDate(term.effectiveFrom);
					const status =
						term === inForce
							? "in-force"
							: !ended && term.effectiveFrom > todayIso
								? "planned"
								: null;
					return (
						<li key={term.effectiveFrom} className={ROW}>
							<span className="[grid-area:from] text-[11.5px] text-muted-foreground whitespace-nowrap font-bold font-mono">
								From {when}
							</span>
							<span className="[grid-area:st] inline-flex gap-1.5 items-center justify-self-end">
								{status && <StatusPill status={status} />}
								<span className={OPS}>
									<button
										type="button"
										onClick={() => setEditor({ mode: "edit", index })}
										disabled={anyPending}
										aria-label={`Edit term from ${when}`}
										className={OP}
									>
										<Pencil className="w-[11px] h-[11px]" aria-hidden="true" />
									</button>
									<button
										type="button"
										onClick={() => handleRemove(index)}
										disabled={anyPending || terms.length <= 1}
										aria-label={`Remove term from ${when}`}
										title={terms.length <= 1 ? "A contract needs at least one term" : undefined}
										className={cn(OP, "hover:text-destructive")}
									>
										{pendingIndex === index ? (
											<Loader2 className="w-[11px] h-[11px] animate-spin" aria-hidden="true" />
										) : (
											<Trash2 className="w-[11px] h-[11px]" aria-hidden="true" />
										)}
									</button>
								</span>
							</span>
							<span className="[grid-area:what] min-w-0 text-foreground font-medium">
								{describeTerm(term)}
							</span>
							{term.note && (
								<span className="[grid-area:note] text-xs text-muted-foreground truncate">
									“{term.note}”
								</span>
							)}
						</li>
					);
				})}
			</ul>

			<div className="mt-3.5">
				<Button
					ref={setChangeButton}
					type="button"
					variant="secondary"
					size="sm"
					onClick={() => setEditor({ mode: "add" })}
					disabled={anyPending}
				>
					<Plus aria-hidden="true" />
					Change contract from…
				</Button>
			</div>

			{(project.goalOverrides ?? []).length > 0 && (
				<div className="mt-4">
					<h4 className={LABEL}>Goal overrides</h4>
					<OverrideList project={project} todayIso={todayIso} />
				</div>
			)}

			<div className="mt-2.5 pt-2.5 border-t border-border text-xs text-muted-foreground leading-[1.6] font-medium">
				{!contract.holidayCountry && (
					<p className="text-destructive-ink">
						Public holidays are not deducted.
						<button
							type="button"
							onClick={() => onOpenSettings("holidayCountry")}
							className={CONST_BUTTON}
						>
							Set region
						</button>
					</p>
				)}
				<p>
					{constants}
					<button
						type="button"
						onClick={() => onOpenSettings("holidayCountry")}
						className={CONST_BUTTON}
						aria-label="Edit the region, the opening balance and the end"
					>
						Edit
					</button>
				</p>
			</div>

			{editor && (
				<TermDialog
					key={editor.mode === "edit" ? `edit-${editor.index}` : "add"}
					title={editor.mode === "edit" ? "Edit term" : "Change contract from…"}
					initial={
						editor.mode === "edit"
							? termFormDefaults(editing)
							: // A new term starts from the current numbers, dated today.
								termFormDefaults(current ?? terms[terms.length - 1], {
									effectiveFrom: todayIso,
									note: "",
								})
					}
					takenDates={otherDates}
					submitting={anyPending}
					returnFocus={() => changeButton.current}
					onClose={() => setEditor(null)}
					onSave={(term, onError) => {
						const nextTerms =
							editor.mode === "edit"
								? terms.map((t, i) => (i === editor.index ? term : t))
								: [...terms, term];
						const savedIndex = sortTerms(nextTerms).indexOf(term);
						const nextContract: Contract = { ...contract, terms: sortTerms(nextTerms) };
						updateContract.mutate(
							{ projectId: project.id, contract: toApiContract(nextContract) },
							{
								onSuccess: () => {
									toast.success(editor.mode === "edit" ? "Term updated" : "Contract changed");
									setEditor(null);
								},
								onError: (err) => onError(err, savedIndex),
							},
						);
					}}
				/>
			)}
		</Panel>
	);
}

function GoalVariant({
	project,
	todayIso,
	firstTrackedIso,
	onOpenSettings,
}: {
	project: ProjectWithDuration;
	todayIso: string;
	firstTrackedIso?: string;
	onOpenSettings: (field: ProjectFormAutoFocusField) => void;
}) {
	const monday = mondayOfIso(todayIso);
	const overrides = project.goalOverrides ?? [];
	const permanents = overrides
		.filter((o): o is GoalOverride & { effectiveFrom: string } => !!o.effectiveFrom)
		.sort((a, b) => a.effectiveFrom.localeCompare(b.effectiveFrom));
	// The header's kind chip reads the same resolution.
	const { weeklyGoal: goal, goalType, override: inForce } = standingGoalOn(project, monday);
	const base = project.weeklyGoal ?? null;
	const same = (a: GoalOverride, b: GoalOverride) =>
		a.weeklyGoal === b.weeklyGoal && (a.goalType ?? goalType) === (b.goalType ?? goalType);

	// Since when the goal has been what it is: back through the permanent
	// overrides that set the same figure, else the project's first session.
	let since: string | undefined;
	if (inForce) {
		let k = permanents.indexOf(inForce as (typeof permanents)[number]);
		while (k > 0 && same(permanents[k - 1], inForce)) k -= 1;
		since = permanents[k]?.effectiveFrom;
	} else {
		since = firstTrackedIso;
	}
	const next = permanents.find((o) => o.effectiveFrom > monday);

	const goalLabel = (hours: number | null) =>
		hours == null ? "no goal" : `${hoursLabel(hours)} / week`;
	const steps: ChartStep[] = [];
	if (
		firstTrackedIso &&
		(permanents.length === 0 || firstTrackedIso < permanents[0].effectiveFrom)
	) {
		steps.push({ date: firstTrackedIso, hours: base, label: goalLabel(base) });
	}
	for (const o of permanents) {
		steps.push({ date: o.effectiveFrom, hours: o.weeklyGoal, label: goalLabel(o.weeklyGoal) });
	}
	const chartLabel = `Weekly goal over time: ${steps
		.map((s) => `${s.hours == null ? "no goal" : hoursLabel(s.hours)} from ${plainDate(s.date)}`)
		.join("; ")}`;

	const dayJobWithoutContract = project.kind === "day_job";

	return (
		<Panel role="region" aria-label="Goal" padding="px-6 py-[22px]">
			<div className="flex items-baseline gap-x-3 gap-y-2 flex-wrap">
				<h3 className={LABEL}>Goal</h3>
				<button
					type="button"
					onClick={() => onOpenSettings("weeklyGoal")}
					className={cn(LINKISH, "ml-auto")}
				>
					Edit goal
				</button>
			</div>
			<div className="mt-3">
				<p className={BIG2}>
					{goal == null ? "No weekly goal" : `${hoursLabel(goal)} / week · ${goalType}`}
				</p>
				<p className="text-[12.5px] text-muted-foreground mt-0.5 font-medium">
					{goal == null
						? "Set one and each week is measured against it."
						: since
							? `since ${longDate(since)}`
							: "the project's own goal"}
				</p>
			</div>
			{next && (
				<p className="mt-2 text-[13px] text-tint-holiday-ink font-bold leading-[1.45]">
					<span className="text-muted-foreground font-medium">Next</span> →{" "}
					{next.weeklyGoal == null
						? "No goal"
						: `${hoursLabel(next.weeklyGoal)} / week · ${next.goalType ?? goalType}`}{" "}
					from {longDate(next.effectiveFrom)}
				</p>
			)}
			{steps.length >= 2 && <StepChart steps={steps} todayIso={todayIso} label={chartLabel} />}

			{overrides.length > 0 ? (
				<OverrideList project={project} todayIso={todayIso} />
			) : (
				<p className="mt-3 pt-2.5 border-t border-border text-xs text-muted-foreground font-medium">
					No overrides. A week's goal under Earlier weeks sets one.
				</p>
			)}

			{dayJobWithoutContract && (
				<p className="mt-2.5 pt-2.5 border-t border-border text-xs text-muted-foreground font-medium leading-[1.6]">
					No contract yet
					<button
						type="button"
						onClick={() => onOpenSettings("scheduleType")}
						className={CONST_BUTTON}
					>
						Add contract
					</button>
				</p>
			)}
		</Panel>
	);
}

export function ContractRegister({
	project,
	todayIso,
	firstTrackedIso,
	onOpenSettings,
	changeButtonRef,
}: ContractRegisterProps) {
	const contract = project.kind === "day_job" ? project.contract : undefined;
	if (contract) {
		return (
			<ContractVariant
				project={project}
				contract={contract}
				todayIso={todayIso}
				onOpenSettings={onOpenSettings}
				changeButtonRef={changeButtonRef}
			/>
		);
	}
	const hasPersonalGoal = project.weeklyGoal != null || (project.goalOverrides ?? []).length > 0;
	if (project.kind === "day_job" && !hasPersonalGoal) {
		return (
			<Panel role="region" aria-label="Contract" padding="px-6 py-[22px]">
				<h3 className={LABEL}>Contract</h3>
				{/* The standing says what a contract brings; the rail only names the state. */}
				<p className="mt-2.5 text-xs text-muted-foreground font-medium leading-[1.6]">
					No contract yet
					<button
						type="button"
						onClick={() => onOpenSettings("scheduleType")}
						className={CONST_BUTTON}
					>
						Add contract
					</button>
				</p>
			</Panel>
		);
	}
	return (
		<GoalVariant
			project={project}
			todayIso={todayIso}
			firstTrackedIso={firstTrackedIso}
			onOpenSettings={onOpenSettings}
		/>
	);
}

interface TermDialogProps {
	title: string;
	initial: TermFormValues;
	/** effective_from dates of the other terms — no two may start on one day. */
	takenDates: string[];
	submitting: boolean;
	onClose: () => void;
	/** Hands the term over; `onError` brings a failed save's 422 back to the inputs. */
	onSave: (term: ContractTerm, onError: (err: unknown, savedIndex: number) => void) => void;
	/** Where focus goes on close when the control that opened the dialog has gone. */
	returnFocus?: () => HTMLElement | null | undefined;
}

function TermDialog({
	title,
	initial,
	takenDates,
	submitting,
	onClose,
	onSave,
	returnFocus,
}: TermDialogProps) {
	const [values, setValues] = useState<TermFormValues>(initial);
	const [errors, setErrors] = useState<TermFieldErrors>({});
	const [general, setGeneral] = useState<string[]>([]);

	const handleSubmit = () => {
		const next = validateTerm(values);
		if (!next.effectiveFrom && takenDates.includes(values.effectiveFrom)) {
			next.effectiveFrom = "Another term already starts on this day";
		}
		setErrors(next);
		setGeneral([]);
		if (Object.keys(next).length > 0) return;
		onSave(termFromForm(values), (err, savedIndex) => {
			// PUT /contract's body is the contract itself, so paths start at "terms".
			const sorted = contractFieldErrors(apiFieldErrors(err), "", savedIndex);
			setErrors(sorted.term);
			const messages = [...sorted.general];
			if (messages.length === 0 && Object.keys(sorted.term).length === 0) {
				messages.push(describeError(err, "Failed to save contract"));
			}
			setGeneral(messages);
		});
	};

	return (
		<Dialog
			open
			onClose={onClose}
			returnFocus={returnFocus}
			title={title}
			description="Any weekday works: a change on a Wednesday charges Monday and Tuesday at the old rate."
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					handleSubmit();
				}}
				className="space-y-4"
				noValidate
			>
				<ContractTermFields
					values={values}
					onChange={setValues}
					errors={errors}
					dateLabel="From"
					withNote
					autoFocusField="effectiveFrom"
				/>
				{general.length > 0 && (
					<div className="text-sm text-destructive-ink space-y-0.5" role="alert">
						{general.map((message) => (
							<p key={message}>{message}</p>
						))}
					</div>
				)}
				<div className="flex gap-2 pt-1">
					<Button type="submit" disabled={submitting} className="flex-1">
						{submitting ? "Saving…" : "Save term"}
					</Button>
					<Button type="button" variant="outline" onClick={onClose}>
						Cancel
					</Button>
				</div>
			</form>
		</Dialog>
	);
}
