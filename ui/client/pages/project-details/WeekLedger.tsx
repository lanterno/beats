/**
 * WeekLedger — "Earlier weeks", newest first: one line per closed week with
 * its seven day cells, the adjusted expectation (or the goal), the hours,
 * the difference and the running balance; a rule row on the date every
 * term changed, and runs of empty weeks folded into one quiet line. The
 * rows are `ledgerRows` over `/ledger` (docs/project-page-roadmap.md,
 * Decision 11): nothing here reconstructs a figure.
 *
 * The goal cell on a week the contract does not govern opens the override
 * popover; on a governed week the figure is the contract's and not offered.
 */

import { useState } from "react";
import { toast } from "sonner";
import type {
	GoalOverride,
	Ledger,
	LedgerNote,
	LedgerNoteKind,
	LedgerWeek,
	LedgerWeekRow,
	ProjectWithDuration,
	RuleRow,
} from "@/entities/project";
import {
	balanceTone,
	contractGovernsWeek,
	describeLedgerNote,
	formatSignedHours,
	ledgerCsv,
	ledgerRows,
	useUpdateGoalOverrides,
} from "@/entities/project";
import { describeError } from "@/shared/api";
import { addIsoDays, cn, mondayOfIso, parseIsoDate } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { hoursTotal, longDate, shortDate } from "./dates";
import { GoalOverridePopover } from "./GoalOverridePopover";
import { CELL_TINT, LABEL, LINKISH, SUB, TINT, TONE } from "./styles";

export interface WeekLedgerProps {
	project: ProjectWithDuration;
	todayIso: string;
	ledger?: Ledger;
	isLoading?: boolean;
	error?: unknown;
	/** How many weeks the ledger was asked for. */
	weeks: number;
	onShowMore: () => void;
	onOpenWeek: (weekOf: string) => void;
	/** The week open in the Days panel, marked in its row. */
	openWeekOf?: string;
	/** The project's session count, for the all-time line. */
	sessionCount: number;
}

/** The API's ceiling on `weeks`. */
const MAX_WEEKS = 104;
const STEP = 5;

// Under 640 px of the content column the table becomes a two-line grid per
// week: the label with the delta on the first line, the cells, worked,
// expected and balance on the second — the mockup's container query. The
// variants are written out in full because Tailwind reads them off the
// source text; a template would leave them uncompiled.
const TH = `${LABEL} text-[10px] text-right px-2 pt-1.5 pb-2 whitespace-nowrap`;
const TD =
	"px-2 py-[9px] border-t border-border text-[13.5px] font-bold text-right whitespace-nowrap align-middle font-mono text-foreground @max-[640px]/content:border-0 @max-[640px]/content:p-0 @max-[640px]/content:text-left @max-[640px]/content:min-w-0";

/**
 * A week's notes as its "why" line: a run of the same kind on consecutive
 * days is one range ("Mon Jul 20 – Fri Jul 24 · vacation"), anything else
 * the entity's wording ("Tue Aug 18 · sick ½", "Mon May 25 · Whit Monday").
 */
function describeNotes(notes: LedgerNote[]): string[] {
	const out: string[] = [];
	let i = 0;
	while (i < notes.length) {
		const first = notes[i];
		let j = i;
		while (
			first.kind !== "holiday" &&
			j + 1 < notes.length &&
			notes[j + 1].kind === first.kind &&
			notes[j + 1].halfDay === first.halfDay &&
			addIsoDays(notes[j].date, 1) === notes[j + 1].date
		) {
			j += 1;
		}
		if (j > i) {
			const half = first.halfDay ? " ½" : "";
			out.push(`${shortDate(first.date)} – ${shortDate(notes[j].date)} · ${first.kind}${half}`);
		} else {
			out.push(describeLedgerNote(first));
		}
		i = j + 1;
	}
	return out;
}

function weeksBetween(fromIso: string, toIso: string): number {
	const from = parseIsoDate(fromIso);
	const to = parseIsoDate(toIso);
	if (!from || !to) return 0;
	return Math.round((to.getTime() - from.getTime()) / (7 * 86_400_000));
}

/** The seven day cells, scaled to the largest day shown, tinted by the day's note. */
function Cells({ week, max }: { week: LedgerWeek; max: number }) {
	const tints = new Map<number, LedgerNoteKind>();
	for (const note of week.notes) {
		const d = parseIsoDate(note.date);
		if (d) tints.set((d.getDay() + 6) % 7, note.kind);
	}
	return (
		<span
			className="inline-grid grid-cols-[repeat(7,8px)] gap-[3px] items-end h-4 align-middle"
			aria-hidden="true"
		>
			{week.days.map((hours, i) => {
				const tint = tints.get(i);
				const key = `${week.weekOf}-${i}`;
				if (hours <= 0 && !tint) {
					return <i key={key} className="block h-[3px] rounded-sm bg-border" />;
				}
				const height = tint && hours <= 0 ? 6 : Math.max(3, Math.round((hours / max) * 16));
				return (
					<i
						key={key}
						className={cn(
							"block rounded-t-[3px] rounded-b-px min-h-[3px]",
							tint ? CELL_TINT[tint] : "bg-success/55",
						)}
						style={{ height: `${height}px` }}
					/>
				);
			})}
		</span>
	);
}

/** A rule row as the mockup's green pill; a planned one the neutral ghost. */
function RulePill({ row }: { row: RuleRow }) {
	return (
		<div
			className={cn(
				"rounded-full px-3.5 py-[9px] font-body text-[12.5px] font-bold text-left",
				row.planned
					? "bg-tint-other text-muted-foreground"
					: "bg-tint-holiday text-tint-holiday-ink",
			)}
		>
			{row.text}
			{row.sub && " "}
			{row.sub && <span className="text-muted-foreground ml-2 font-medium">{row.sub}</span>}
		</div>
	);
}

function Delta({ delta }: { delta: number | null }) {
	if (delta === null) return <span className="text-muted-foreground font-medium">—</span>;
	const tone = balanceTone(delta);
	const text =
		tone === "even" ? "0.0" : `${tone === "over" ? "+" : "−"}${Math.abs(delta).toFixed(1)}`;
	return (
		<span className={tone === "even" ? "text-muted-foreground font-medium" : TONE[tone]}>
			{text}
		</span>
	);
}

export function WeekLedger({
	project,
	todayIso,
	ledger,
	isLoading,
	error,
	weeks,
	onShowMore,
	onOpenWeek,
	openWeekOf,
	sessionCount,
}: WeekLedgerProps) {
	const [popoverWeek, setPopoverWeek] = useState<string | null>(null);
	const updateGoalOverrides = useUpdateGoalOverrides();

	const dayJob = project.kind === "day_job";
	const contract = dayJob ? project.contract : undefined;
	const withBalance = dayJob && !!contract;
	const since = ledger?.since ?? null;
	const thisMonday = mondayOfIso(todayIso);

	// Back to the opening balance and no further: weeks before the contract
	// carry no figure the ledger is for.
	const shown: Ledger | undefined = ledger
		? {
				...ledger,
				weeks: since ? ledger.weeks.filter((w) => addIsoDays(w.weekOf, 6) >= since) : ledger.weeks,
			}
		: undefined;
	const rows = shown ? ledgerRows(shown, project, todayIso) : [];
	const weekRows = rows.filter((r): r is LedgerWeekRow => r.type === "week");
	const maxDay = Math.max(0.1, ...weekRows.flatMap((r) => r.week.days));

	const oldest =
		shown && shown.weeks.length > 0 ? shown.weeks[shown.weeks.length - 1].weekOf : null;
	const moreBack = since && oldest ? Math.max(0, weeksBetween(mondayOfIso(since), oldest)) : null;
	const canShowMore = weeks < MAX_WEEKS && (moreBack === null || moreBack > 0);

	const saveOverrides = (overrides: GoalOverride[], done: string) => {
		updateGoalOverrides.mutate(
			{
				projectId: project.id,
				overrides: overrides.map((o) => ({
					week_of: o.weekOf ?? null,
					effective_from: o.effectiveFrom ?? null,
					weekly_goal: o.weeklyGoal,
					goal_type: o.goalType ?? null,
				})),
			},
			{
				onSuccess: () => {
					setPopoverWeek(null);
					toast.success(done);
				},
				onError: (err) => toast.error(describeError(err, "Failed to save override")),
			},
		);
	};

	const handleSaveOverride = (
		mondayIso: string,
		values: { weeklyGoal: number | null; goalType: "target" | "cap"; scope: "week" | "permanent" },
	) => {
		const overrides = project.goalOverrides ?? [];
		if (values.scope === "week") {
			saveOverrides(
				[
					...overrides.filter((o) => o.weekOf !== mondayIso),
					{ weekOf: mondayIso, weeklyGoal: values.weeklyGoal, goalType: values.goalType },
				],
				"Goal override saved",
			);
		} else {
			saveOverrides(
				[
					...overrides.filter((o) => o.effectiveFrom !== mondayIso),
					{ effectiveFrom: mondayIso, weeklyGoal: values.weeklyGoal, goalType: values.goalType },
				],
				"Goal override saved",
			);
		}
	};

	const handleRemoveOverride = (mondayIso: string) => {
		saveOverrides(
			(project.goalOverrides ?? []).filter(
				(o) => o.weekOf !== mondayIso && o.effectiveFrom !== mondayIso,
			),
			"Override removed",
		);
	};

	const findDirectOverride = (mondayIso: string): GoalOverride | undefined =>
		(project.goalOverrides ?? []).find(
			(o) => o.weekOf === mondayIso || o.effectiveFrom === mondayIso,
		);

	const copyCsv = async () => {
		try {
			await navigator.clipboard.writeText(ledgerCsv(rows));
			toast.success("Copied as CSV");
		} catch {
			toast.error("Could not copy to the clipboard");
		}
	};

	const columns = withBalance ? 6 : 5;
	const totals = ledger?.totals ?? null;
	const opening = contract?.openingBalanceHours ?? 0;
	const allTime = hoursTotal((project.totalMinutes || 0) / 60);

	return (
		<Panel role="region" aria-label="Earlier weeks" padding="px-6 py-[22px]">
			<div className="flex items-baseline gap-x-3 gap-y-2 flex-wrap">
				<h3 className={LABEL}>
					Earlier weeks <span className={SUB}>newest first</span>
				</h3>
				<div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
					<span className={`@max-[640px]/content:hidden`}>
						day cells scale to the largest day shown · tints:{" "}
						<span className={cn("rounded-full px-1.5 text-[10.5px] font-bold", TINT.vacation)}>
							vacation
						</span>{" "}
						<span className={cn("rounded-full px-1.5 text-[10.5px] font-bold", TINT.sick)}>
							sick
						</span>{" "}
						<span className={cn("rounded-full px-1.5 text-[10.5px] font-bold", TINT.holiday)}>
							holiday
						</span>
					</span>
					{weekRows.length > 0 && (
						<button
							type="button"
							onClick={copyCsv}
							className={cn(LINKISH, "ml-2.5 whitespace-nowrap")}
						>
							Copy as CSV
						</button>
					)}
				</div>
			</div>

			{isLoading ? (
				<p className="mt-3 text-[13px] text-muted-foreground">Loading…</p>
			) : error ? (
				<p className="mt-3 text-[13px] text-destructive" role="alert">
					{describeError(error, "Could not load the earlier weeks")}
				</p>
			) : weekRows.length === 0 ? (
				<div className="mt-3 flex flex-col gap-1.5">
					{rows
						.filter((r): r is RuleRow => r.type === "rule")
						.map((row) => (
							<RulePill key={`${row.rule}-${row.date}`} row={row} />
						))}
					<p className="px-1.5 text-[13px] text-muted-foreground">
						{since && mondayOfIso(since) >= thisMonday
							? "No earlier weeks — the contract started this week."
							: "No earlier weeks yet."}
					</p>
				</div>
			) : (
				<table
					className={`w-full border-separate border-spacing-0 mt-3 @max-[640px]/content:block`}
				>
					<thead className={`@max-[640px]/content:hidden`}>
						<tr>
							<th className={cn(TH, "text-left")}>Week</th>
							<th className={cn(TH, "text-left")} aria-label="Days" />
							<th className={TH}>{withBalance ? "Expected" : "Goal"}</th>
							<th className={TH}>Worked</th>
							<th className={TH}>+/−</th>
							{withBalance && <th className={TH}>Balance</th>}
						</tr>
					</thead>
					<tbody className={`@max-[640px]/content:block`}>
						{rows.map((row) => {
							if (row.type === "rule") {
								return (
									<tr
										key={`rule-${row.rule}-${row.date}`}
										className={`@max-[640px]/content:block @max-[640px]/content:my-1.5`}
									>
										<td colSpan={columns} className={`px-0 py-1 @max-[640px]/content:block`}>
											<RulePill row={row} />
										</td>
									</tr>
								);
							}
							if (row.type === "quiet") {
								return (
									<tr
										key={`quiet-${row.weeks[0]?.weekOf}`}
										className={`@max-[640px]/content:block @max-[640px]/content:my-1.5`}
									>
										<td
											colSpan={columns}
											className={`text-center text-[12.5px] font-medium text-muted-foreground p-1.5 @max-[640px]/content:block`}
										>
											{row.text}
										</td>
									</tr>
								);
							}

							const { week } = row;
							const governed =
								contractGovernsWeek(project, week.weekOf) || week.contractExpected !== null;
							// The contract's expectation is a computed figure, one decimal like
							// the cells beside it ("0.0" on a week off); a goal is as entered ("8").
							const goalText =
								week.contractExpected !== null
									? week.contractExpected.toFixed(1)
									: week.effectiveGoal !== null
										? `${Math.round(week.effectiveGoal * 100) / 100}`
										: week.effectiveGoalOverridden || governed
											? "No goal"
											: "—";
							const why = [
								...describeNotes(week.notes),
								...(week.effectiveGoalOverridden && !governed ? ["override"] : []),
							].join(" · ");
							const direct = findDirectOverride(week.weekOf);
							const open = popoverWeek === week.weekOf;
							const current = week.weekOf === openWeekOf;

							return (
								<tr
									key={week.weekOf}
									aria-current={current ? "true" : undefined}
									onClick={(e) => {
										if ((e.target as HTMLElement).closest("button, input, [role=dialog]")) return;
										onOpenWeek(week.weekOf);
									}}
									className={cn(
										"cursor-pointer hover:bg-secondary",
										current && "bg-secondary",
										`@max-[640px]/content:grid @max-[640px]/content:grid-cols-[auto_auto_auto_minmax(0,1fr)] @max-[640px]/content:[grid-template-areas:'week_week_week_delta'_'cells_w_x_bal'] @max-[640px]/content:gap-x-2.5 @max-[640px]/content:gap-y-[3px] @max-[640px]/content:px-1 @max-[640px]/content:py-[9px] @max-[640px]/content:border-t @max-[640px]/content:border-border @max-[640px]/content:items-center`,
									)}
								>
									<td
										className={cn(TD, "text-left font-body @max-[640px]/content:[grid-area:week]")}
									>
										<button
											type="button"
											onClick={() => onOpenWeek(week.weekOf)}
											className={cn(
												"font-extrabold text-[13.5px] text-foreground rounded",
												"focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
											)}
											aria-label={`Open ${row.label}, ${row.range}`}
										>
											{row.label}
										</button>
										<span className="text-muted-foreground text-xs ml-2 font-mono font-medium">
											{row.range}
										</span>
										{why && (
											<span className="block text-xs mt-px font-medium text-muted-foreground">
												{why}
											</span>
										)}
									</td>
									<td className={cn(TD, "text-left @max-[640px]/content:[grid-area:cells]")}>
										<Cells week={week} max={maxDay} />
									</td>
									<td
										className={`${TD} text-muted-foreground font-medium min-w-[5ch] @max-[640px]/content:[grid-area:x] @max-[640px]/content:before:content-['of_']`}
									>
										{governed ? (
											<span
												title={
													week.contractExpected !== null
														? "Set by the contract: the hours expected this week after holidays and absences"
														: "Set by the contract"
												}
											>
												{goalText}
											</span>
										) : (
											<span className="relative inline-block">
												<button
													type="button"
													onClick={() => setPopoverWeek(open ? null : week.weekOf)}
													className={cn(
														"hover:underline decoration-dotted underline-offset-2 rounded focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
														week.effectiveGoalOverridden && "italic",
													)}
													title={
														week.effectiveGoalOverridden
															? "Goal override active — click to edit"
															: "Click to set goal override"
													}
												>
													{goalText}
												</button>
												{open && (
													<GoalOverridePopover
														currentGoal={week.effectiveGoal ?? project.weeklyGoal ?? null}
														currentGoalType={week.effectiveGoalType}
														hasExistingOverride={direct !== undefined}
														existingOverrideIsNull={
															direct !== undefined && direct.weeklyGoal == null
														}
														onSave={(values) => handleSaveOverride(week.weekOf, values)}
														onRemove={() => handleRemoveOverride(week.weekOf)}
														onClose={() => setPopoverWeek(null)}
													/>
												)}
											</span>
										)}
									</td>
									<td className={`${TD} min-w-[5ch] @max-[640px]/content:[grid-area:w]`}>
										{week.worked > 0 ? (
											week.worked.toFixed(1)
										) : (
											<span className="text-muted-foreground font-medium">—</span>
										)}
									</td>
									<td
										className={`${TD} @max-[640px]/content:[grid-area:delta] @max-[640px]/content:text-right`}
									>
										<Delta delta={row.delta} />
									</td>
									{withBalance && (
										<td
											className={`${TD} font-extrabold min-w-[5ch] @max-[640px]/content:[grid-area:bal] @max-[640px]/content:text-right @max-[640px]/content:text-muted-foreground @max-[640px]/content:font-bold @max-[640px]/content:before:content-['bal_']`}
										>
											{week.balanceEnd === null ? (
												<span className="text-muted-foreground font-medium">—</span>
											) : balanceTone(week.balanceEnd) === "even" ? (
												<span className="text-muted-foreground font-medium">0.0</span>
											) : (
												formatSignedHours(week.balanceEnd).replace(/ h$/, "")
											)}
										</td>
									)}
								</tr>
							);
						})}
					</tbody>
				</table>
			)}

			{canShowMore && weekRows.length > 0 && (
				<div className="flex justify-center gap-2 items-baseline pt-3.5 pb-1 text-[12.5px]">
					<button type="button" onClick={onShowMore} className={LINKISH}>
						Show {STEP} more weeks
					</button>
					{moreBack !== null && (
						<span className="text-muted-foreground">
							· {moreBack} more back to the opening balance
						</span>
					)}
				</div>
			)}

			<div className="flex flex-wrap gap-x-[18px] gap-y-1.5 text-xs text-muted-foreground font-medium pt-3 px-2 mt-2 border-t border-border">
				{totals && since && (
					<span>
						Since {longDate(since)} ·{" "}
						<b className="text-foreground font-extrabold">{totals.expected.toFixed(1)} h</b>{" "}
						expected ·{" "}
						<b className="text-foreground font-extrabold">{totals.worked.toFixed(1)} h</b> worked ·{" "}
						<b className="text-foreground font-extrabold">
							{formatSignedHours(totals.worked - totals.expected)}
						</b>
						{balanceTone(opening) !== "even" && ` (${formatSignedHours(opening)} brought forward)`}
					</span>
				)}
				<span>
					All time <b className="text-foreground font-extrabold">{allTime}</b> ·{" "}
					<b className="text-foreground font-extrabold">
						{sessionCount.toLocaleString("en-US")} session{sessionCount === 1 ? "" : "s"}
					</b>
				</span>
			</div>
		</Panel>
	);
}
