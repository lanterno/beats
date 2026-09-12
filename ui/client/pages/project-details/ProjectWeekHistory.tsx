import type { Dispatch, SetStateAction } from "react";
import { useState } from "react";
import { toast } from "sonner";
import type { GoalOverride } from "@/entities/project";
import { useUpdateGoalOverrides } from "@/entities/project";
import { describeError } from "@/shared/api";
import { cn } from "@/shared/lib";
import { GoalOverridePopover } from "./GoalOverridePopover";

const WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

export interface WeekRow {
	label: string;
	weeksAgo: number;
	mondayIso: string;
	days: number[];
	total: number;
	effectiveGoal: number | null;
	effectiveGoalType: "target" | "cap";
	effectiveGoalOverridden: boolean;
	/**
	 * The contract sets this week's goal (its term's nominal hours, which the
	 * API reports as the effective goal), and reads no override on it: the
	 * figure is shown, and the override popover is not offered — terms change
	 * in the contract history panel.
	 */
	contractGoverned: boolean;
}

interface ProjectWeekHistoryProps {
	rows: WeekRow[];
	/** Whether any week in view has a goal — decides the grid's column count. */
	hasAnyGoal: boolean;
	/** Monday=0 … Sunday=6, for highlighting today's column. */
	todayDayIndex: number;
	plannedByMonday: Map<string, number>;
	commitsByMonday: Map<string, number>;
	hasGitHubRepo: boolean;
	projectId: string;
	weeklyGoal: number | null | undefined;
	goalOverrides: GoalOverride[];
	/** Set when a week is selected; the session list below reads it. */
	scopedWeeksAgo: number | null;
	onScopeWeek: Dispatch<SetStateAction<number | null>>;
	onShowMoreWeeks: () => void;
}

/**
 * The per-week grid: seven day cells, totals, goal, planned hours and commits.
 *
 * Goal overrides live here in full — the popover, the save and the removal.
 * They are edited from this table and nowhere else, and the page above was
 * carrying the popover's open state only so its save handler could close it.
 *
 * `scopedWeeksAgo` stays a prop because clicking a week label here filters the
 * session list below.
 */
export function ProjectWeekHistory({
	rows,
	hasAnyGoal,
	todayDayIndex,
	plannedByMonday,
	commitsByMonday,
	hasGitHubRepo,
	projectId,
	weeklyGoal,
	goalOverrides,
	scopedWeeksAgo,
	onScopeWeek,
	onShowMoreWeeks,
}: ProjectWeekHistoryProps) {
	const [overridePopoverWeek, setOverridePopoverWeek] = useState<number | null>(null);
	const updateGoalOverridesMutation = useUpdateGoalOverrides();

	const handleSaveOverride = (
		mondayIso: string,
		values: {
			weeklyGoal: number | null;
			goalType: "target" | "cap";
			scope: "week" | "permanent";
		},
	) => {
		const overrides = [...(goalOverrides || [])];

		if (values.scope === "week") {
			// Remove any existing one-off for this week
			const filtered = overrides.filter((o) => o.weekOf !== mondayIso);
			filtered.push({
				weekOf: mondayIso,
				weeklyGoal: values.weeklyGoal,
				goalType: values.goalType,
			});
			saveOverrides(filtered);
		} else {
			// Permanent: remove any existing permanent with the same effective_from
			const filtered = overrides.filter((o) => o.effectiveFrom !== mondayIso);
			filtered.push({
				effectiveFrom: mondayIso,
				weeklyGoal: values.weeklyGoal,
				goalType: values.goalType,
			});
			saveOverrides(filtered);
		}
	};
	const handleRemoveOverride = (mondayIso: string) => {
		const overrides = (goalOverrides || []).filter(
			(o) => o.weekOf !== mondayIso && o.effectiveFrom !== mondayIso,
		);
		saveOverrides(overrides);
	};
	const saveOverrides = (overrides: GoalOverride[]) => {
		updateGoalOverridesMutation.mutate(
			{
				projectId: projectId,
				overrides: overrides.map((o) => ({
					week_of: o.weekOf ?? null,
					effective_from: o.effectiveFrom ?? null,
					weekly_goal: o.weeklyGoal,
					goal_type: o.goalType ?? null,
				})),
			},
			{
				onSuccess: () => {
					setOverridePopoverWeek(null);
					toast.success("Goal override saved");
				},
				onError: (err) => toast.error(describeError(err, "Failed to save override")),
			},
		);
	};

	const findDirectOverride = (mondayIso: string): GoalOverride | undefined =>
		(goalOverrides || []).find((o) => o.weekOf === mondayIso || o.effectiveFrom === mondayIso);

	return (
		<section className="mt-6" aria-label="Week history">
			<div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden">
				{/* Header */}
				<div
					className={`grid ${hasAnyGoal ? "grid-cols-[72px_repeat(7,1fr)_64px_56px_100px_56px]" : "grid-cols-[72px_repeat(7,1fr)_64px_56px_64px]"} px-3 py-2 border-b border-border/60`}
				>
					<div />
					{WEEKDAY_SHORT.map((d, i) => (
						<div
							key={d}
							className={`text-center text-[10px] uppercase tracking-widest ${
								i === todayDayIndex ? "text-accent font-semibold" : "text-muted-foreground"
							}`}
						>
							{d}
						</div>
					))}
					<div
						className="text-right text-[10px] uppercase tracking-widest text-muted-foreground"
						title="Planned hours for this project this week"
					>
						Planned
					</div>
					<div
						className="text-right text-[10px] uppercase tracking-widest text-muted-foreground"
						title="Commits to the linked GitHub repo this week"
					>
						Commits
					</div>
					<div className="text-right text-[10px] uppercase tracking-widest text-muted-foreground">
						Total
					</div>
					{hasAnyGoal && (
						<div className="text-right text-[10px] uppercase tracking-widest text-muted-foreground">
							+/-
						</div>
					)}
				</div>

				{/* Week rows */}
				{rows.map((row, rowIdx) => {
					const rowHours = row.total / 60;
					const rowGoal = row.effectiveGoal;
					const rowGoalType = row.effectiveGoalType;
					const goalMet = rowGoal ? rowHours >= rowGoal : false;
					const goalPctRow = rowGoal ? Math.min((rowHours / rowGoal) * 100, 100) : 0;
					const directOverride = findDirectOverride(row.mondayIso);
					const hasDirectOverride = directOverride !== undefined;
					const directOverrideIsNull = hasDirectOverride && directOverride?.weeklyGoal == null;
					// Trust the server-resolved flag. It covers both one-off and
					// permanent overrides (including weeks past an effective_from).
					const isOverridden = row.effectiveGoalOverridden;
					// A null goal is "No goal" when something said so — an override, or
					// a contract term of 0 hours (a sabbatical) — and "—" when nothing
					// sets one at all.
					const saysNoGoal = isOverridden || row.contractGoverned;
					const goalText =
						rowGoal != null
							? row.total > 0
								? `${rowHours.toFixed(1)}/${rowGoal}h`
								: `—/${rowGoal}h`
							: saysNoGoal
								? "No goal"
								: row.total > 0
									? `${rowHours.toFixed(1)}h`
									: "—";
					const goalClass =
						rowGoal != null
							? goalMet
								? "text-green-400"
								: "text-accent"
							: saysNoGoal
								? "text-muted-foreground"
								: "text-muted-foreground/50";

					return (
						<div
							key={row.label}
							className={`grid ${hasAnyGoal ? "grid-cols-[72px_repeat(7,1fr)_64px_56px_100px_56px]" : "grid-cols-[72px_repeat(7,1fr)_64px_56px_64px]"} px-3 py-1.5 border-b border-border/20 last:border-b-0 ${
								rowIdx === 0 ? "bg-secondary/10" : "hover:bg-secondary/10"
							}`}
						>
							<button
								type="button"
								onClick={() =>
									onScopeWeek((current) => (current === row.weeksAgo ? null : row.weeksAgo))
								}
								aria-pressed={scopedWeeksAgo === row.weeksAgo}
								title={
									scopedWeeksAgo === row.weeksAgo
										? "Click to clear the sessions scope"
										: "Click to scope the sessions list to this week"
								}
								className={cn(
									"text-xs truncate pr-1 text-left rounded transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40",
									scopedWeeksAgo === row.weeksAgo
										? "text-accent font-medium"
										: "text-muted-foreground hover:text-foreground",
								)}
							>
								{row.label}
							</button>
							{row.days.map((mins, i) => (
								<div
									key={i}
									className={`text-center text-xs tabular-nums ${
										mins > 0
											? rowIdx === 0 && i === todayDayIndex
												? "text-accent font-medium"
												: "text-foreground"
											: "text-muted-foreground/30"
									}`}
								>
									{mins > 0 ? `${(mins / 60).toFixed(1)}` : "—"}
								</div>
							))}
							<PlannedCell hours={plannedByMonday.get(row.mondayIso)} />
							<CommitsCell count={commitsByMonday.get(row.mondayIso)} hasRepo={hasGitHubRepo} />
							{hasAnyGoal ? (
								<>
									<div className="relative flex flex-col items-end gap-0.5">
										{row.contractGoverned ? (
											<span
												className={`text-sm font-medium tabular-nums ${goalClass}`}
												title="Set by the contract: its weekly hours before holidays and absences — change its terms in the contract history"
											>
												{goalText}
											</span>
										) : (
											<button
												type="button"
												onClick={() =>
													setOverridePopoverWeek(
														overridePopoverWeek === row.weeksAgo ? null : row.weeksAgo,
													)
												}
												className={`text-sm font-medium tabular-nums cursor-pointer hover:underline decoration-dotted underline-offset-2 ${goalClass} ${isOverridden ? "italic" : ""}`}
												title={
													isOverridden
														? "Goal override active — click to edit"
														: "Click to set goal override"
												}
											>
												{goalText}
											</button>
										)}
										{row.total > 0 && rowGoal != null && (
											<div className="w-full h-1 rounded-full bg-muted/40 overflow-hidden">
												<div
													className={`h-full rounded-full transition-all ${
														rowGoalType === "cap"
															? goalPctRow >= 90
																? "bg-red-400"
																: "bg-accent/70"
															: goalMet
																? "bg-green-400"
																: "bg-accent/70"
													}`}
													style={{ width: `${goalPctRow}%` }}
												/>
											</div>
										)}
										{!row.contractGoverned && overridePopoverWeek === row.weeksAgo && (
											<GoalOverridePopover
												currentGoal={rowGoal ?? weeklyGoal ?? null}
												currentGoalType={rowGoalType}
												hasExistingOverride={hasDirectOverride}
												existingOverrideIsNull={directOverrideIsNull}
												onSave={(values) => handleSaveOverride(row.mondayIso, values)}
												onRemove={() => {
													handleRemoveOverride(row.mondayIso);
													setOverridePopoverWeek(null);
													toast.success("Override removed");
												}}
												onClose={() => setOverridePopoverWeek(null)}
											/>
										)}
									</div>
									<div className="text-right text-xs tabular-nums self-center">
										{row.total > 0 && rowGoal != null ? (
											<span className={goalMet ? "text-green-400" : "text-red-400"}>
												{goalMet ? "+" : ""}
												{(rowHours - rowGoal).toFixed(1)}h
											</span>
										) : (
											<span className="text-muted-foreground/30">—</span>
										)}
									</div>
								</>
							) : (
								<div className="text-right text-sm font-medium tabular-nums text-accent">
									{row.total > 0 ? `${rowHours.toFixed(1)}h` : "—"}
								</div>
							)}
						</div>
					);
				})}

				{/* Show more weeks */}
				<button
					type="button"
					onClick={() => onShowMoreWeeks()}
					className="w-full py-2 text-sm text-accent hover:bg-accent/5 transition-colors border-t border-border/40"
				>
					Show 5 more weeks...
				</button>
			</div>
		</section>
	);
}

function PlannedCell({ hours }: { hours: number | undefined }) {
	if (hours === undefined) {
		return (
			<div
				className="text-right text-xs tabular-nums text-muted-foreground/30"
				title="No plan entry for this week"
			>
				—
			</div>
		);
	}
	return (
		<div className="text-right text-xs tabular-nums text-muted-foreground" title="Planned hours">
			{hours.toFixed(1)}h
		</div>
	);
}

function CommitsCell({ count, hasRepo }: { count: number | undefined; hasRepo: boolean }) {
	if (!hasRepo) {
		return (
			<div
				className="text-right text-xs tabular-nums text-muted-foreground/30"
				title="Link a GitHub repo to see weekly commit counts here"
			>
				—
			</div>
		);
	}
	const n = count ?? 0;
	if (n === 0) {
		return (
			<div
				className="text-right text-xs tabular-nums text-muted-foreground/40"
				title="No commits this week"
			>
				0
			</div>
		);
	}
	return (
		<div
			className="text-right text-xs tabular-nums text-muted-foreground"
			title={`${n} commits this week`}
		>
			{n}
		</div>
	);
}
