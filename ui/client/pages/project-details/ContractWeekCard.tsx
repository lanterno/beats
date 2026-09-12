/**
 * ContractWeekCard — one week of a day job against its contract: the hours
 * it expected, the hours worked, what remains (or by how much the week is
 * already over), the five weekdays with their holiday or absence, and the
 * running balance. The numbers are the API's (docs/work-contracts-roadmap.md,
 * "The arithmetic"); this card only says them so the sign cannot be missed.
 *
 * The balance is as of today whichever week is shown — it is one figure,
 * not a per-week one, and the API sends it whenever today's term owes
 * hours — so the line says so and sits under every week alike. A week with
 * no expectation by nature (an objective term, a term of 0 hours, a week
 * before the contract) shows the hours worked and the personal goal if
 * there is one, which is what the API resolves for such a week.
 */

import { ChevronLeft, ChevronRight } from "lucide-react";
import { type Ref, useId, useState } from "react";
import { ABSENCE_TYPE_LABELS } from "@/entities/absence";
import type {
	BalanceTone,
	Contract,
	ContractDay,
	ContractDayAbsence,
	ContractTerm,
	ContractWeek,
} from "@/entities/project";
import { balanceTone, describeBalance, termOn, useContractWeek } from "@/entities/project";
import { describeError } from "@/shared/api";
import { cn, formatDateShort, parseIsoDate, todayIso } from "@/shared/lib";
import { getMondayIsoFor } from "./weekIso";

interface ContractWeekCardProps {
	projectId: string;
	contract: Contract;
	/** The personal weekly goal, for a week the contract does not govern. */
	personalGoal: number | null;
	/** The section, so the header's figure can bring the reader here. */
	ref?: Ref<HTMLElement>;
}

const WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri"] as const;

// The absence calendar's colours, so a day reads the same on both.
const ABSENCE_STYLES: Record<ContractDayAbsence["type"], string> = {
	vacation: "bg-accent/20 border-accent/50",
	sick: "bg-destructive/15 border-destructive/50",
	other: "bg-secondary border-muted-foreground/40",
};

const BALANCE_CLASS: Record<BalanceTone, string> = {
	over: "text-success",
	owed: "text-destructive",
	even: "text-muted-foreground",
};

function hours(n: number): string {
	return `${n.toFixed(1)} h`;
}

function weekLabel(offset: number): string {
	if (offset === 0) return "This week";
	if (offset === -1) return "Last week";
	if (offset === 1) return "Next week";
	return offset < 0 ? `${-offset} weeks ago` : `In ${offset} weeks`;
}

function weekRange(mondayIso: string): string {
	const monday = parseIsoDate(mondayIso);
	if (!monday) return mondayIso;
	const sunday = new Date(monday);
	sunday.setDate(monday.getDate() + 6);
	return `${formatDateShort(monday)} — ${formatDateShort(sunday)}`;
}

function longDate(iso: string): string {
	const d = parseIsoDate(iso);
	return d
		? d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })
		: iso;
}

export function ContractWeekCard({
	projectId,
	contract,
	personalGoal,
	ref,
}: ContractWeekCardProps) {
	const [offset, setOffset] = useState(0);
	const headingId = useId();
	// Explicit Monday rather than the API's default, so the header's query
	// for the current week and this one share a key.
	const weekOf = getMondayIsoFor(-offset);
	const { data: week, isLoading, error } = useContractWeek(projectId, weekOf);

	return (
		<section
			ref={ref}
			id="contract-week"
			tabIndex={-1}
			aria-labelledby={headingId}
			className="mt-6 rounded-lg border border-border/80 bg-card shadow-soft p-3 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
		>
			<header className="flex flex-wrap items-center gap-1.5 mb-3">
				<h3
					id={headingId}
					className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground"
				>
					Week against the contract
				</h3>
				<div className="ml-auto flex items-center gap-1">
					<button
						type="button"
						onClick={() => setOffset((o) => o - 1)}
						aria-label="Previous week"
						className="p-1 rounded text-muted-foreground/70 hover:text-foreground hover:bg-secondary/60 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
					>
						<ChevronLeft className="w-4 h-4" />
					</button>
					<span className="text-xs text-foreground text-center min-w-24" aria-live="polite">
						{weekLabel(offset)}
						<span className="text-muted-foreground/70 ml-1.5 hidden sm:inline tabular-nums">
							{weekRange(weekOf)}
						</span>
					</span>
					<button
						type="button"
						onClick={() => setOffset((o) => o + 1)}
						aria-label="Next week"
						className="p-1 rounded text-muted-foreground/70 hover:text-foreground hover:bg-secondary/60 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
					>
						<ChevronRight className="w-4 h-4" />
					</button>
					{offset !== 0 && (
						<button
							type="button"
							onClick={() => setOffset(0)}
							className="px-2 py-0.5 rounded-md text-xs text-accent hover:bg-accent/10 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
						>
							Today
						</button>
					)}
				</div>
			</header>

			{isLoading ? (
				<p className="text-xs text-muted-foreground">Loading…</p>
			) : error ? (
				<p className="text-xs text-destructive" role="alert">
					{describeError(error, "Could not load the week")}
				</p>
			) : week ? (
				<>
					{week.expected === undefined ? (
						<UngovernedWeek
							week={week}
							personalGoal={personalGoal}
							term={termOn(contract, weekOf)}
						/>
					) : (
						<GovernedWeek week={week} expected={week.expected} />
					)}
					{week.balance !== undefined && (
						<p className="mt-3 text-xs text-muted-foreground">
							Balance as of today:{" "}
							<span
								className={cn("font-medium tabular-nums", BALANCE_CLASS[balanceTone(week.balance)])}
							>
								{describeBalance(week.balance)}
							</span>
						</p>
					)}
				</>
			) : null}
		</section>
	);
}

function GovernedWeek({ week, expected }: { week: ContractWeek; expected: number }) {
	// Rounded once, to the decimal shown, so −0.04 h is neither "over" nor
	// a signed zero ("-0.0 h"): the `|| 0` turns the −0 that rounding
	// leaves into 0.
	const remaining = Number((week.remaining ?? expected - week.worked).toFixed(1)) || 0;
	const isOver = remaining < 0;
	// The same rounding, so a two-minute Saturday does not announce "+ 0.0 h".
	const weekendHours = Number(
		week.days
			.slice(5)
			.reduce((sum, d) => sum + d.worked, 0)
			.toFixed(1),
	);
	const today = todayIso();

	return (
		<>
			<dl className="flex flex-wrap gap-x-6 gap-y-2">
				<Stat label="Expected" value={hours(expected)} />
				<Stat label="Worked" value={hours(week.worked)} />
				{isOver ? (
					<Stat label="Over this week" value={hours(-remaining)} tone="over" />
				) : (
					<Stat label="Remaining" value={hours(remaining)} />
				)}
			</dl>
			<ProgressBar worked={week.worked} expected={expected} />

			<ol className="mt-3 grid grid-cols-5 gap-1" aria-label="Weekdays">
				{week.days.slice(0, 5).map((day, i) => (
					<DayCell
						key={day.date}
						day={day}
						weekday={WEEKDAY_SHORT[i]}
						isToday={day.date === today}
					/>
				))}
			</ol>
			{weekendHours > 0 && (
				<p className="mt-1 text-[11px] text-muted-foreground">
					+ {hours(weekendHours)} at the weekend, counted in worked.
				</p>
			)}
		</>
	);
}

function UngovernedWeek({
	week,
	personalGoal,
	term,
}: {
	week: ContractWeek;
	personalGoal: number | null;
	/** The term in force on the week's Monday; undefined before the contract starts. */
	term: ContractTerm | undefined;
}) {
	return (
		<>
			<dl className="flex flex-wrap gap-x-6 gap-y-2">
				<Stat label="Worked" value={hours(week.worked)} />
				{personalGoal != null && <Stat label="Personal goal" value={hours(personalGoal)} />}
			</dl>
			{personalGoal != null && <ProgressBar worked={week.worked} expected={personalGoal} />}
			<p className="mt-2 text-[11px] text-muted-foreground">
				{term === undefined
					? "Before the contract starts: nothing is expected yet."
					: term.scheduleType === "objective"
						? "An objective-based term: no weekly expectation."
						: "A term of 0 hours: no weekly expectation."}
			</p>
		</>
	);
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: BalanceTone }) {
	return (
		<div className="min-w-0">
			<dt className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</dt>
			<dd
				className={cn(
					"font-heading text-lg font-semibold tabular-nums",
					tone ? BALANCE_CLASS[tone] : "text-foreground",
				)}
			>
				{value}
			</dd>
		</div>
	);
}

function ProgressBar({ worked, expected }: { worked: number; expected: number }) {
	if (expected <= 0) return null;
	const pct = Math.min((worked / expected) * 100, 100);
	const met = worked >= expected;
	return (
		<div className="mt-2 h-1.5 w-full rounded-full bg-muted/40 overflow-hidden" aria-hidden="true">
			<div
				className={cn("h-full rounded-full transition-all", met ? "bg-success" : "bg-accent/70")}
				style={{ width: `${pct}%` }}
			/>
		</div>
	);
}

function DayCell({
	day,
	weekday,
	isToday,
}: {
	day: ContractDay;
	weekday: string;
	isToday: boolean;
}) {
	const { holiday, absence } = day;
	const style = holiday
		? "border-success/40 bg-success/10"
		: absence
			? ABSENCE_STYLES[absence.type]
			: "border-border/40 bg-background/40";
	return (
		<li
			className={cn(
				"rounded-md border px-2 py-1.5 text-xs",
				style,
				isToday && "ring-2 ring-accent/60",
			)}
			title={`${longDate(day.date)}: ${hours(day.worked)} worked of ${hours(day.expected)} expected`}
		>
			<div className="flex items-baseline justify-between gap-1">
				<span
					className={cn(
						"text-[10px] uppercase tracking-wider",
						isToday ? "text-accent font-semibold" : "text-muted-foreground",
					)}
				>
					{weekday}
				</span>
				<span
					className={cn(
						"tabular-nums",
						day.worked > 0 ? "text-foreground" : "text-muted-foreground/40",
					)}
				>
					{day.worked > 0 ? hours(day.worked) : "—"}
				</span>
			</div>
			{holiday ? (
				<span className="block text-[10px] leading-tight text-success truncate" title={holiday}>
					Holiday · {holiday}
				</span>
			) : absence ? (
				<span className="block text-[10px] leading-tight font-medium text-foreground">
					{ABSENCE_TYPE_LABELS[absence.type]}
					{absence.halfDay ? " ½" : ""}
				</span>
			) : (
				<span className="block text-[10px] leading-tight text-muted-foreground/60 tabular-nums">
					of {hours(day.expected)}
				</span>
			)}
		</li>
	);
}
