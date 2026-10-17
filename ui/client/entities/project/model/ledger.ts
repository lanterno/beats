/**
 * The ledger as the page lays it out: the earlier weeks newest first, with a
 * rule row where the contract's terms changed, where it started and where it
 * ended, an adjustment row for every balance adjustment, and a run of empty
 * weeks folded into one quiet row. Pure and clock-free — `todayIso` decides
 * which week is current (never in the ledger: the standing carries it) and
 * which term is still planned.
 *
 * The copy is the mockup's (docs/project-page-mockup.html): "From Mon Aug 3,
 * 2026 · Part time 80% of 42 h = 33.6 h/wk" over "was 60% · 25.2 h · “note”",
 * "·· 3 weeks away · Jul 6 – 26 · vacation ··".
 */

import { addIsoDays, mondayOfIso } from "@/shared/lib";
import {
	balanceIsFinal,
	formatHours,
	formatSignedHours,
	sortTerms,
	termHoursPerWeek,
	toPercent,
} from "./contract";
import type {
	Contract,
	ContractTerm,
	Ledger,
	LedgerAdjustment,
	LedgerNote,
	LedgerWeek,
	ProjectKind,
} from "./types";
import { dateRange, formatShortDate, longDate, sundayOf, weekNumber, weekRange } from "./weekDates";

export interface LedgerWeekRow {
	type: "week";
	week: LedgerWeek;
	/** "W36". */
	label: string;
	/** "Aug 31 – Sep 6". */
	range: string;
	/** The +/− cell — `weekDelta`. */
	delta: number | null;
}

export interface RuleRow {
	type: "rule";
	rule: "opening" | "term" | "ended";
	/** The day the rule takes effect, YYYY-MM-DD. */
	date: string;
	text: string;
	/** "was 60% · 25.2 h · “Four days a week from August”". */
	sub?: string;
	/** Dated after today: shown as a ghost above the current week. */
	planned: boolean;
}

/**
 * A balance adjustment as its own row: "Sat Aug 8 · Adjusted −40.0 h" over
 * "“Paid out in August”", with the hours it moved the balance by in the
 * +/− column — so reading up the ledger, the close below plus the
 * adjustment rows plus the week's +/− is the week's close.
 */
export interface AdjustmentRow {
	type: "adjustment";
	adjustment: LedgerAdjustment;
	text: string;
	sub?: string;
	/** The +/− cell: the API's `applied`. */
	delta: number;
}

export interface QuietRow {
	type: "quiet";
	text: string;
	/** The folded weeks, newest first. */
	weeks: LedgerWeek[];
}

export type LedgerRow = LedgerWeekRow | RuleRow | AdjustmentRow | QuietRow;

/** "Tue Aug 18 · sick ½", "Mon May 25 · Whit Monday" — a week's note as the row's "why". */
export function describeLedgerNote(note: LedgerNote): string {
	const when = formatShortDate(note.date);
	if (note.kind === "holiday") return `${when} · ${note.name ?? "holiday"}`;
	return `${when} · ${note.kind}${note.halfDay ? " ½" : ""}`;
}

/** "Part time 80% of 42 h = 33.6 h/wk" — a term as its rule row states it. */
function termRule(term: ContractTerm): string {
	const weekly = termHoursPerWeek(term);
	switch (term.scheduleType) {
		case "objective":
			return "Objective · no weekly expectation";
		case "full_time":
			return weekly == null ? "Full time" : `Full time · ${formatHours(weekly)}/wk`;
		case "custom":
			return weekly == null ? "Custom" : `Custom · ${formatHours(weekly)}/wk`;
		case "part_time": {
			if (weekly == null || term.fullTimeHours == null || term.percentage == null) {
				return "Part time";
			}
			const pct = toPercent(term.percentage);
			return `Part time ${pct}% of ${formatHours(term.fullTimeHours)} = ${formatHours(weekly)}/wk`;
		}
	}
}

/** "was 60% · 25.2 h" — the term a change replaced, in its shortest form. */
function wasRule(term: ContractTerm): string {
	const weekly = termHoursPerWeek(term);
	switch (term.scheduleType) {
		case "objective":
			return "was objective";
		case "full_time":
			return weekly == null ? "was full time" : `was full time · ${formatHours(weekly)}`;
		case "custom":
			return weekly == null ? "was custom" : `was ${formatHours(weekly)}`;
		case "part_time":
			return weekly == null || term.percentage == null
				? "was part time"
				: `was ${toPercent(term.percentage)}% · ${formatHours(weekly)}`;
	}
}

/** "−40.0 h", "+8.0 h", "0.0 h" — an adjustment's hours as entered, at one decimal. */
function hoursText(hours: number, signed: boolean): string {
	const magnitude = Math.abs(hours).toFixed(1);
	if (magnitude === "0.0") return "0.0 h";
	if (hours < 0) return `−${magnitude} h`;
	return signed ? `+${magnitude} h` : `${magnitude} h`;
}

/**
 * An adjustment as its row states it. A delta is its signed hours; a reset
 * names the target and the balance it replaced ("was +62.5 h", its hours less
 * what it applied); a cap names the ceiling and what it took off.
 */
function adjustmentRow(adjustment: LedgerAdjustment): AdjustmentRow {
	const when = formatShortDate(adjustment.date);
	const note = adjustment.note ? `“${adjustment.note}”` : null;
	let text: string;
	let detail: string | null = null;
	switch (adjustment.kind) {
		case "delta":
			text = `Adjusted ${hoursText(adjustment.hours, true)}`;
			break;
		case "reset":
			text = `Balance reset to ${hoursText(adjustment.hours, false)}`;
			detail = `was ${formatSignedHours(adjustment.hours - adjustment.applied)}`;
			break;
		case "cap": {
			text = `Capped at ${hoursText(adjustment.hours, false)}`;
			const dropped = -adjustment.applied;
			detail =
				dropped.toFixed(1) === "0.0"
					? "under the cap, nothing dropped"
					: `${dropped.toFixed(1)} h over the cap dropped`;
			break;
		}
	}
	const sub = [detail, note].filter((part): part is string => part !== null).join(" · ");
	return {
		type: "adjustment",
		adjustment,
		text: `${when} · ${text}`,
		sub: sub || undefined,
		delta: adjustment.applied,
	};
}

/** Every rule the contract puts in the ledger, dated; placement is decided below. */
function contractRules(contract: Contract, ledger: Ledger, todayIso: string): RuleRow[] {
	const terms = sortTerms(contract.terms);
	const rules: RuleRow[] = terms.map((term, i) => {
		const planned = term.effectiveFrom > todayIso;
		if (i === 0) {
			const opening = contract.openingBalanceHours;
			const forward =
				formatSignedHours(opening) === "even"
					? "nothing brought forward"
					: `brought forward ${formatSignedHours(opening)}`;
			return {
				type: "rule",
				rule: "opening",
				date: term.effectiveFrom,
				text: `Contract starts ${longDate(term.effectiveFrom)} · ${termRule(term)}${planned ? " · planned" : ""}`,
				sub: forward,
				planned,
			};
		}
		const sub = [wasRule(terms[i - 1]), term.note ? `“${term.note}”` : null]
			.filter((part): part is string => part !== null)
			.join(" · ");
		return {
			type: "rule",
			rule: "term",
			date: term.effectiveFrom,
			text: `From ${longDate(term.effectiveFrom)} · ${termRule(term)}${planned ? " · planned" : ""}`,
			sub: sub || undefined,
			planned,
		};
	});
	const endedOn = contract.endedOn;
	if (endedOn) {
		const planned = endedOn > todayIso;
		// The close on the end day, before a settlement after it, which is its
		// own row. On the last day itself the balance is still live (the
		// standing carries it), so the rule says the contract ended, as the
		// header and the register do that day, and gives no final figure.
		const final = ledger.endedBalance;
		const finalText =
			final !== null && balanceIsFinal(contract, todayIso)
				? ` · final balance ${formatSignedHours(final)}`
				: "";
		rules.push({
			type: "rule",
			rule: "ended",
			date: endedOn,
			text: planned
				? `Ends ${longDate(endedOn)} · planned`
				: `Ended ${longDate(endedOn)}${finalText}`,
			planned,
		});
	}
	return rules;
}

/**
 * A week with nothing to show: worked 0, and on a week the contract governs
 * nothing owed; elsewhere no goal and no override either — a missed goal is a
 * figure, and its cell is where the week's "No goal" override is set.
 */
function isQuiet(week: LedgerWeek): boolean {
	if (week.worked !== 0) return false;
	if (week.contractExpected !== null) return week.contractExpected === 0;
	return week.effectiveGoal === null && !week.effectiveGoalOverridden;
}

function quietRow(run: LedgerWeek[]): QuietRow {
	const newest = run[0];
	const oldest = run[run.length - 1];
	const notes = run.flatMap((w) => w.notes);
	const away = notes.length > 0 && notes.every((n) => n.kind === "vacation");
	const text = away
		? `·· ${run.length} weeks away · ${dateRange(oldest.weekOf, sundayOf(newest.weekOf))} · vacation ··`
		: `·· ${run.length} quiet weeks ··`;
	return { type: "quiet", text, weeks: run };
}

/** Consecutive week rows that are all quiet, two or more of them, become one quiet row. */
function collapseQuiet(rows: LedgerRow[]): LedgerRow[] {
	const out: LedgerRow[] = [];
	let run: LedgerWeekRow[] = [];
	const flush = () => {
		if (run.length >= 2) out.push(quietRow(run.map((row) => row.week)));
		else out.push(...run);
		run = [];
	};
	for (const row of rows) {
		if (row.type === "week" && isQuiet(row.week)) {
			run.push(row);
			continue;
		}
		flush();
		out.push(row);
	}
	flush();
	return out;
}

function roundHours(hours: number): number {
	return Math.round(hours * 100) / 100;
}

/** Σ applied over the ledger's adjustments dated in [from, to]. */
function appliedBetween(ledger: Ledger, from: string, to: string): number {
	return ledger.weeks
		.flatMap((w) => w.adjustments)
		.filter((a) => from <= a.date && a.date <= to)
		.reduce((sum, a) => sum + a.applied, 0);
}

/**
 * A week's +/−: on a week with a close, the API's `balanceMoved` — what the
 * balance counted that week less what it expected, adjustments left out,
 * read off the close before even when the ledger does not hold that week.
 * The balance counts only the contract's days under a term that owes hours,
 * so on the week a contract starts or ends, or a term that owes nothing
 * begins or ends, worked − expected is not what moved it.
 *
 * An API that predates `balanceMoved` leaves the SPA to read the move off
 * the closes: between its close and the one before when both are in the
 * ledger; on the contract's first close — the week holding `since`, or the
 * week after when the one holding it has no close (a weekend start) — from
 * the opening balance. Either leaves out the balance adjustments inside it,
 * which are rows of their own: the week's own, or on the first close every
 * one from `since` through the week's Sunday. Else, and on a week with no
 * close, worked − expected, else worked − goal; null with neither, and for a
 * week the ledger does not hold. `openingBalance` is the contract's; null off
 * a contract.
 */
export function weekDelta(
	ledger: Ledger,
	weekOf: string,
	openingBalance: number | null,
): number | null {
	const week = ledger.weeks.find((w) => w.weekOf === weekOf);
	if (!week) return null;
	const older = ledger.weeks.find((w) => w.weekOf === addIsoDays(weekOf, -7));
	if (week.balanceEnd !== null) {
		if (typeof week.balanceMoved === "number") return week.balanceMoved;
		const sunday = sundayOf(weekOf);
		if (older && older.balanceEnd !== null) {
			const applied = appliedBetween(ledger, weekOf, sunday);
			return roundHours(week.balanceEnd - older.balanceEnd - applied);
		}
		const startWeek = ledger.since === null ? null : mondayOfIso(ledger.since);
		const firstClose = startWeek === weekOf || (older !== undefined && startWeek === older.weekOf);
		if (openingBalance !== null && firstClose && ledger.since !== null) {
			const applied = appliedBetween(ledger, ledger.since, sunday);
			return roundHours(week.balanceEnd - openingBalance - applied);
		}
	}
	if (week.contractExpected !== null) return roundHours(week.worked - week.contractExpected);
	if (week.effectiveGoal !== null) return roundHours(week.worked - week.effectiveGoal);
	return null;
}

function weekRow(week: LedgerWeek, delta: number | null): LedgerWeekRow {
	return {
		type: "week",
		week,
		label: weekNumber(week.weekOf),
		range: weekRange(week.weekOf),
		delta,
	};
}

/**
 * The rows of the "Earlier weeks" panel, newest first. The current week is
 * left out. A term's rule sits under the week its date falls in (reading
 * down, everything above it is under the new terms), the opening rule
 * likewise under the contract's first week, the closing rule above the week
 * the contract ended in. An adjustment row is placed as a term's rule is,
 * under its week. A rule or an adjustment dated in the current week or later
 * sits at the top, a rule a ghost when it is still to come. One older than
 * the oldest week shown is not shown: the ledger has not reached it yet.
 */
export function ledgerRows(
	ledger: Ledger,
	project: { kind: ProjectKind; contract?: Contract },
	todayIso: string,
): LedgerRow[] {
	const thisMonday = mondayOfIso(todayIso);
	const weeks = [...ledger.weeks]
		.filter((w) => w.weekOf < thisMonday)
		.sort((a, b) => b.weekOf.localeCompare(a.weekOf));
	const contract = project.kind === "day_job" ? project.contract : undefined;
	const rules = contract ? contractRules(contract, ledger, todayIso) : [];
	const adjustments = contract ? ledger.weeks.flatMap((w) => w.adjustments).map(adjustmentRow) : [];
	const dated = (row: RuleRow | AdjustmentRow) =>
		row.type === "rule" ? row.date : row.adjustment.date;
	const newestFirst = (a: RuleRow | AdjustmentRow, b: RuleRow | AdjustmentRow) =>
		dated(b).localeCompare(dated(a));
	const marks: (RuleRow | AdjustmentRow)[] = [...adjustments, ...rules];

	const rows: LedgerRow[] = [];
	// Rules and adjustments from the current week on, newest first, above everything.
	rows.push(...marks.filter((r) => mondayOfIso(dated(r)) >= thisMonday).sort(newestFirst));
	const opening = contract ? contract.openingBalanceHours : null;
	for (const week of weeks) {
		const inWeek = marks.filter((r) => mondayOfIso(dated(r)) === week.weekOf);
		const isEnded = (r: RuleRow | AdjustmentRow) => r.type === "rule" && r.rule === "ended";
		rows.push(...inWeek.filter(isEnded));
		rows.push(weekRow(week, weekDelta(ledger, week.weekOf, opening)));
		rows.push(...inWeek.filter((r) => !isEnded(r)).sort(newestFirst));
	}
	return collapseQuiet(rows);
}

function csvCell(value: string | number | null): string {
	if (value === null) return "";
	const text = String(value);
	return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/**
 * The rows as CSV: `week,expected,worked,delta,balance`, the week as its
 * Monday's ISO date, a blank where a figure is null; a side project's goal
 * stands in the expected column. Rule and quiet rows are one line each, the
 * text in the first cell; an adjustment row is its text and its applied
 * hours in the delta column, so the column still adds up to the balance.
 */
export function ledgerCsv(rows: LedgerRow[]): string {
	const lines = ["week,expected,worked,delta,balance"];
	for (const row of rows) {
		if (row.type === "week") {
			const { week } = row;
			lines.push(
				[
					week.weekOf,
					csvCell(week.contractExpected ?? week.effectiveGoal),
					csvCell(week.worked),
					csvCell(row.delta),
					csvCell(week.balanceEnd),
				].join(","),
			);
		} else if (row.type === "adjustment") {
			const text = row.sub ? `${row.text} · ${row.sub}` : row.text;
			lines.push(`${csvCell(text)},,,${csvCell(row.delta)},`);
		} else {
			const text = row.type === "rule" && row.sub ? `${row.text} · ${row.sub}` : row.text;
			lines.push(`${csvCell(text)},,,,`);
		}
	}
	return `${lines.join("\n")}\n`;
}
