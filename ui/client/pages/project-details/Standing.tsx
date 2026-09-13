/**
 * Standing — the brightest panel: where you stand with the employer as of
 * today (the balance with its three-term proof and the Sunday projection),
 * and what that makes of the open week (Expected · Worked · Remaining, the
 * nominal line, one sentence, the action). On a side project the left is
 * the four-week average and the week runs against the personal goal.
 *
 * Every figure is the API's — `/contract/week` and `/ledger` — and every
 * sentence is `entities/project/model/standing.ts`; this component only
 * lays them out (docs/project-page-roadmap.md, "The page" and "States").
 */

import { Loader2, Plus, ZapOff } from "lucide-react";
import { toast } from "sonner";
import { useDismissInboxItem, useProjectHealth } from "@/entities/intelligence";
import type {
	ContractWeek,
	Ledger,
	LedgerWeek,
	ProjectKind,
	ProjectWithDuration,
} from "@/entities/project";
import {
	balanceTone,
	formatSignedHours,
	isFirstWeek,
	isTimeBasedOn,
	nominalLine,
	projection,
	sortTerms,
	termHoursPerWeek,
	termOn,
	weekDelta,
	weekLabel,
	weekNumber,
	weekRange,
	weekSentence,
} from "@/entities/project";
import { describeError } from "@/shared/api";
import { addIsoDays, cn, getDayName, mondayOfIso, parseIsoDate } from "@/shared/lib";
import { Button, Panel } from "@/shared/ui";
import { longDate, shortDate } from "./dates";
import { BIG_TONE, LABEL, LIVE_DOT } from "./styles";

export interface StandingProps {
	project: ProjectWithDuration;
	todayIso: string;
	/** The open week's Monday. */
	openWeekOf: string;
	/** `/contract/week` for the current week — the balance is pinned to today. */
	currentWeek?: ContractWeek;
	/** Why the current week could not be read: the balance says so instead of waiting. */
	currentWeekError?: unknown;
	/** `/contract/week` for the open week; the same object when it is the current one. */
	openWeek?: ContractWeek;
	openWeekError?: unknown;
	/** The following week, for "then Mon 6.7 h". */
	nextWeek?: ContractWeek;
	ledger?: Ledger;
	ledgerLoading?: boolean;
	ledgerError?: unknown;
	/** The timer runs on this project. */
	running: boolean;
	onBookTimeOff: () => void;
	onEditGoal: () => void;
	onAddContract: () => void;
	onSetRegion: () => void;
}

const WHEN = "font-body normal-case tracking-normal font-medium text-[12.5px]";
const BIG =
	"font-heading font-extrabold text-[50px] @max-[420px]/content:text-[42px] leading-none tracking-[-0.035em] mt-2 whitespace-nowrap";
const BIG_WORD = "font-body text-[17px] font-medium tracking-normal ml-2 text-muted-foreground";
const PROOF = "mt-3 text-[12.5px] leading-[1.9] text-muted-foreground";
const PROJ = "mt-2.5 text-[13px] leading-[1.55] text-foreground font-medium";
const NOTICE =
	"mt-2.5 text-[13px] leading-normal flex gap-2.5 items-center flex-wrap text-muted-foreground";
const FIG_K = `${LABEL} text-[10px]`;
const FIG_V =
	"font-heading text-[26px] font-extrabold tracking-[-0.02em] leading-[1.2] mt-0.5 flex items-center gap-2 text-foreground";

function hours1(hours: number): string {
	return `${hours.toFixed(1)} h`;
}

/** A goal at the precision it was entered: "8 h", "7.5 h" — as the chip and the ledger write it. */
function goalHours(hours: number): string {
	return `${Math.round(hours * 100) / 100} h`;
}

const ALERT = "mt-2.5 text-[13px] leading-normal text-destructive text-pretty";

/** "+2.0 h" for a balance term, "0.0 h" where the chip would say "even". */
function signed(hours: number): string {
	const text = formatSignedHours(hours);
	return text === "even" ? "0.0 h" : text;
}

/** The lead sentence in bold, the rest plain — the mockup's `<b>` on the first clause. */
function Sentence({ text }: { text: string }) {
	const m = /^(.+?\.)(?=\s|$)([\s\S]*)$/.exec(text);
	return (
		<p className="mt-2.5 text-[15.5px] leading-normal text-foreground text-pretty">
			{m ? (
				<>
					<b className="font-bold">{m[1]}</b>
					{m[2]}
				</>
			) : (
				text
			)}
		</p>
	);
}

/** "This project has been quiet for a while." + Snooze 7d, when the intelligence says so. */
function HealthNotice({ projectId }: { projectId: string }) {
	const { data: healths } = useProjectHealth();
	const dismiss = useDismissInboxItem();
	const health = (healths ?? []).find((h) => h.project_id === projectId);
	if (!health?.alert) return null;
	const text =
		health.alert === "stale_project" ? "This project has been quiet for a while." : health.alert;
	return (
		<p className={NOTICE}>
			<span>{text}</span>
			<Button
				type="button"
				variant="secondary"
				size="sm"
				className="h-7 px-3 text-xs"
				disabled={dismiss.isPending}
				onClick={() =>
					dismiss.mutate(`project_health:${projectId}`, {
						onSuccess: () => toast.success("Snoozed for 7 days"),
						onError: (err) => toast.error(describeError(err, "Failed to snooze")),
					})
				}
			>
				{dismiss.isPending ? (
					<Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" />
				) : (
					<ZapOff className="w-3 h-3" aria-hidden="true" />
				)}
				Snooze 7d
			</Button>
		</p>
	);
}

/** "−840.0 h expected through Wed": the weekday alone inside the current week, dated outside it. */
function throughDay(asOf: string, todayIso: string): string {
	const through = addIsoDays(asOf, -1);
	return mondayOfIso(through) === mondayOfIso(todayIso)
		? getDayName(parseIsoDate(through) ?? new Date(0), "short")
		: shortDate(through);
}

function Balance({
	project,
	todayIso,
	week,
	error,
	onAddContract,
	onSetRegion,
}: {
	project: ProjectWithDuration;
	todayIso: string;
	week?: ContractWeek;
	error?: unknown;
	onAddContract: () => void;
	onSetRegion: () => void;
}) {
	const contract = project.contract;
	if (!contract) {
		return (
			<>
				<p className={LABEL}>Balance</p>
				<p className="mt-2.5 text-[15.5px] leading-normal text-foreground text-pretty">
					No contract yet. Add the terms and the page keeps a balance from that date.
				</p>
				<div className="mt-3.5">
					<Button type="button" variant="secondary" size="sm" onClick={onAddContract}>
						<Plus aria-hidden="true" />
						Add contract
					</Button>
				</div>
			</>
		);
	}

	const ended = contract.endedOn !== undefined && contract.endedOn <= todayIso;
	const term = termOn(contract, todayIso);
	const first = sortTerms(contract.terms)[0];
	const regionNotice = !contract.holidayCountry && (
		<p className={NOTICE}>
			<span>
				Public holidays are not deducted —{" "}
				<button
					type="button"
					onClick={onSetRegion}
					className="text-accent-ink font-bold hover:underline underline-offset-[3px] rounded focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
				>
					set the holiday region
				</button>
			</span>
		</p>
	);

	// Before the first term: that is the "Contract starts" state.
	if (!term && first) {
		const weekly = termHoursPerWeek(first);
		return (
			<>
				<p className={LABEL}>Balance</p>
				<p className="mt-2.5 text-[15.5px] leading-normal text-foreground text-pretty">
					Contract starts {longDate(first.effectiveFrom)}
					{weekly == null ? "" : ` · ${hours1(weekly)}/week`}
				</p>
				{regionNotice}
			</>
		);
	}

	if (!week) {
		return (
			<>
				<p className={LABEL}>Balance</p>
				{error ? (
					<p role="alert" className={ALERT}>
						{describeError(error, "Could not load the balance")}
					</p>
				) : (
					<p className={`${BIG} text-muted-foreground`}>…</p>
				)}
			</>
		);
	}
	// The week route answers with no balance under an objective or 0 h term.
	if (week.balance === undefined || week.balanceAsOf === undefined) {
		const why =
			term?.scheduleType === "objective"
				? "An objective term — no balance while it lasts."
				: "A term of 0 hours — no balance while it lasts.";
		return (
			<>
				<p className={LABEL}>Balance</p>
				<p className="mt-2.5 text-[15.5px] leading-normal text-foreground text-pretty">{why}</p>
				{regionNotice}
			</>
		);
	}

	const tone = balanceTone(week.balance);
	const firstWeek = !ended && isFirstWeek(contract, todayIso);
	const colour = firstWeek ? BIG_TONE.even : BIG_TONE[tone];
	const word = tone === "over" ? "over" : tone === "owed" ? "owed" : "";
	const proj = ended ? null : projection(week, todayIso);
	const since = first ? first.effectiveFrom : week.balanceAsOf;
	const through =
		ended && contract.endedOn
			? shortDate(contract.endedOn)
			: throughDay(week.balanceAsOf, todayIso);

	return (
		<>
			<p className={`${LABEL} flex gap-2 items-baseline flex-wrap`}>
				{ended ? "Final balance" : "Balance"}
				<span className={WHEN}>
					{ended && contract.endedOn
						? `ended ${shortDate(contract.endedOn)}`
						: `as of ${shortDate(week.balanceAsOf)}`}
				</span>
			</p>
			<p className={cn(BIG, colour)} data-tone={firstWeek ? "muted" : tone}>
				{formatSignedHours(week.balance)}
				{word && <small className={BIG_WORD}>{word}</small>}
			</p>
			<p className={PROOF}>
				<span className="block">
					<b className="text-foreground font-extrabold">{signed(week.balanceOpening ?? 0)}</b>{" "}
					brought forward
				</span>
				<span className="block">
					<b className="text-foreground font-extrabold">+{hours1(week.balanceWorked ?? 0)}</b>{" "}
					worked since {shortDate(since)}
				</span>
				<span className="block">
					<b className="text-foreground font-extrabold">
						−{hours1(week.balanceExpectedThrough ?? 0)}
					</b>{" "}
					expected through {through}
				</span>
			</p>
			{firstWeek ? (
				<p className={PROJ}>
					<span className="text-muted-foreground font-normal">First week under the contract.</span>{" "}
					Each day is charged as it closes; the figure settles once a full week is in.
				</p>
			) : proj ? (
				<p className={PROJ}>
					<span className="text-muted-foreground font-normal">By Sunday:</span>{" "}
					{formatSignedHours(proj.met)} if the week is met
					<br />
					{formatSignedHours(proj.stopNow)} if you stop now.
				</p>
			) : null}
			{regionNotice}
		</>
	);
}

/** Goal met when a target is reached, or a cap is kept. */
function goalMet(week: LedgerWeek): boolean {
	if (week.effectiveGoal === null) return false;
	return week.effectiveGoalType === "cap"
		? week.worked <= week.effectiveGoal
		: week.worked >= week.effectiveGoal;
}

function Average({
	kind,
	ledger,
	loading,
	error,
	todayIso,
}: {
	kind: ProjectKind;
	ledger?: Ledger;
	loading?: boolean;
	error?: unknown;
	todayIso: string;
}) {
	const thisMonday = mondayOfIso(todayIso);
	const closed = (ledger?.weeks ?? []).filter((w) => w.weekOf < thisMonday).slice(0, 4);
	const n = closed.length;
	const avg = n > 0 ? closed.reduce((sum, w) => sum + w.worked, 0) / n : null;
	const withGoal = closed.filter((w) => w.effectiveGoal !== null);
	const met = withGoal.filter(goalMet).length;
	const noun = kind === "freelance" ? "freelance work" : "a side project";
	// Until the ledger answers there is no count to state, and "No weeks
	// closed yet" would be a claim about the project.
	const known = !loading && !error && ledger !== undefined;
	return (
		<>
			<p className={LABEL}>{!known || n === 4 ? "4-week average" : `${n}-week average`}</p>
			<div className="mt-2">
				<p className="font-heading text-[26px] font-extrabold tracking-[-0.02em] text-foreground">
					{!known ? (error ? "—" : "…") : avg === null ? "—" : `${avg.toFixed(1)} h / week`}
				</p>
				{error ? (
					<p role="alert" className="text-[13px] text-destructive mt-0.5">
						{describeError(error, "Could not load the earlier weeks")}
					</p>
				) : known ? (
					<p className="text-[13px] text-muted-foreground mt-0.5">
						{n === 0
							? "No weeks closed yet"
							: withGoal.length > 0
								? `Goal met ${met} of the last ${n} weeks`
								: "No goal on the last weeks"}
					</p>
				) : null}
			</div>
			<p className={cn(NOTICE, "mt-3.5")}>
				No contract on {noun} — no balance, nothing owed. The goal is yours.
			</p>
		</>
	);
}

export function Standing(props: StandingProps) {
	const {
		project,
		todayIso,
		openWeekOf,
		currentWeek,
		currentWeekError,
		openWeek,
		openWeekError,
		nextWeek,
		ledger,
		ledgerLoading,
		ledgerError,
		running,
		onBookTimeOff,
		onEditGoal,
		onAddContract,
		onSetRegion,
	} = props;
	const thisMonday = mondayOfIso(todayIso);
	const isCurrent = openWeekOf === thisMonday;
	const isPast = openWeekOf < thisMonday;
	const dayJob = project.kind === "day_job";
	const contract = dayJob ? project.contract : undefined;
	const ended = contract?.endedOn !== undefined && contract.endedOn <= todayIso;
	const ledgerWeek = ledger?.weeks.find((w) => w.weekOf === openWeekOf);

	// On a day job with a contract the open week waits for `/contract/week`
	// (or says why it failed): its figures are the contract's, and the
	// personal goal is no stand-in while the read is on its way.
	const weekPending = dayJob && !!contract && !ended && openWeek === undefined;
	// The contract governs the open week when the week route has an expectation for it.
	const governed = dayJob && !!contract && openWeek?.expected !== undefined && !ended;
	const worked = weekPending ? undefined : (openWeek?.worked ?? ledgerWeek?.worked);

	// The personal goal in force on the open week — the ledger resolves the
	// override; the list's `effective_goal` covers the current week before
	// the ledger answers.
	const goal: number | null =
		ledgerWeek !== undefined
			? ledgerWeek.effectiveGoal
			: isCurrent && project.effectiveGoalOverridden
				? (project.effectiveGoal ?? null)
				: (project.effectiveGoal ?? project.weeklyGoal ?? null);
	const goalType =
		ledgerWeek?.effectiveGoalType ?? project.effectiveGoalType ?? project.goalType ?? "target";
	const goalApplies =
		!governed &&
		!weekPending &&
		!ended &&
		!(dayJob && contract && !termOn(contract, todayIso)) &&
		goal !== null;

	const term = contract ? termOn(contract, openWeekOf) : undefined;
	const nominal = governed && openWeek && term ? nominalLine(openWeek, term) : null;

	const sentence =
		isCurrent && worked !== undefined && !ended
			? weekSentence({
					week: governed && openWeek ? openWeek : { weekOf: openWeekOf, worked },
					nextWeek,
					todayIso,
					kind: project.kind,
					personalGoal: goalApplies ? goal : null,
					goalType,
				})
			: null;

	// A past week: how it closed — never a week still to come. On a governed
	// week that is the balance's move, as the ledger's +/− cell reads it (the
	// contract's first week counts only its own days); the week's remaining
	// stands in when the ledger has not reached the week.
	let closed: string | null = null;
	if (isPast && worked !== undefined) {
		const moved = ledger
			? weekDelta(ledger, openWeekOf, contract?.openingBalanceHours ?? null)
			: null;
		const over =
			governed && openWeek?.expected !== undefined
				? (moved ?? -(openWeek.remaining ?? openWeek.expected - openWeek.worked))
				: goalApplies && goal !== null
					? worked - goal
					: null;
		if (over !== null) {
			const tone = balanceTone(over);
			closed =
				tone === "over"
					? `closed ${formatSignedHours(over)} over`
					: tone === "owed"
						? `closed ${Math.abs(over).toFixed(1)} h short`
						: "closed even";
		}
	}

	const remaining =
		governed && openWeek?.expected !== undefined
			? Math.max(openWeek.remaining ?? openWeek.expected - openWeek.worked, 0)
			: goalApplies && goal !== null && worked !== undefined
				? Math.max(goal - worked, 0)
				: null;

	const label = weekLabel(openWeekOf, todayIso);
	const canBookTimeOff = dayJob && !!contract;
	const canEditGoal = !dayJob || !isTimeBasedOn(contract, todayIso);

	return (
		<Panel
			role="region"
			aria-label="Where you stand"
			padding="p-0"
			className="relative overflow-hidden rounded-[1.875rem] shadow-card"
		>
			<div
				aria-hidden="true"
				className="absolute inset-0 pointer-events-none"
				style={{
					background:
						"radial-gradient(60% 70% at 100% 0%, hsl(var(--accent) / 0.2), transparent 70%), radial-gradient(50% 60% at 0% 100%, hsl(var(--secondary) / 0.16), transparent 70%)",
				}}
			/>
			<div className="relative grid grid-cols-[minmax(0,1fr)] gap-x-8 gap-y-5 px-[26px] pt-6 pb-[22px] @min-[640px]/content:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
				<div className="min-w-0 @min-[640px]/content:pr-[30px]">
					{dayJob ? (
						<Balance
							project={project}
							todayIso={todayIso}
							week={currentWeek}
							error={currentWeekError}
							onAddContract={onAddContract}
							onSetRegion={onSetRegion}
						/>
					) : (
						<Average
							kind={project.kind}
							ledger={ledger}
							loading={ledgerLoading}
							error={ledgerError}
							todayIso={todayIso}
						/>
					)}
					<HealthNotice projectId={project.id} />
				</div>

				<div className="min-w-0">
					<p className={`${LABEL} flex gap-2 items-baseline flex-wrap`}>
						{label}
						<span className={WHEN}>
							{/* "This week · Sep 7 – 13 · W37"; a past week's label already carries its number. */}
							{isCurrent
								? `${weekRange(openWeekOf)} · ${weekNumber(openWeekOf)}`
								: weekRange(openWeekOf)}
						</span>
					</p>
					{weekPending && openWeekError ? (
						<p role="alert" className={ALERT}>
							{describeError(openWeekError, "Could not load the week")}
						</p>
					) : (
						<dl className="flex flex-wrap gap-x-7 gap-y-2 mt-2">
							{governed && openWeek?.expected !== undefined && (
								<div>
									<dt className={FIG_K}>Expected</dt>
									<dd className={FIG_V}>{hours1(openWeek.expected)}</dd>
								</div>
							)}
							{!governed && goalApplies && goal !== null && (
								<div>
									<dt className={FIG_K}>{goalType === "cap" ? "Cap" : "Goal"}</dt>
									<dd className={FIG_V}>{goalHours(goal)}</dd>
								</div>
							)}
							<div>
								<dt className={FIG_K}>Worked</dt>
								<dd className={FIG_V}>
									{worked === undefined ? (weekPending ? "…" : "—") : hours1(worked)}
									{running && isCurrent && (
										<>
											<span className={LIVE_DOT} title="Timer running" aria-hidden="true" />
											<span className="sr-only">, timer running</span>
										</>
									)}
								</dd>
							</div>
							{remaining !== null && (
								<div>
									<dt className={FIG_K}>
										{!governed && goalType === "cap" ? "Under cap" : "Remaining"}
									</dt>
									<dd className={FIG_V}>{hours1(remaining)}</dd>
								</div>
							)}
						</dl>
					)}
					{nominal && <p className="mt-2 text-xs text-muted-foreground">{nominal}</p>}
					{sentence && <Sentence text={sentence} />}
					{closed && (
						<p className="mt-2.5 text-[15.5px] leading-normal text-foreground">
							{label} · {closed}
						</p>
					)}
					{(canBookTimeOff || canEditGoal) && (
						<div className="mt-3.5 flex flex-wrap items-center gap-2.5">
							{canBookTimeOff && (
								<Button type="button" variant="secondary" size="sm" onClick={onBookTimeOff}>
									<Plus aria-hidden="true" />
									Book time off
								</Button>
							)}
							{canEditGoal && (
								<Button type="button" variant="secondary" size="sm" onClick={onEditGoal}>
									Edit goal
								</Button>
							)}
						</div>
					)}
				</div>
			</div>
		</Panel>
	);
}
