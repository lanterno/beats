/**
 * The ledger as the page lays it out: the earlier weeks newest first, with a
 * rule row where the contract's terms changed, where it started and where it
 * ended, and a run of empty weeks folded into one quiet row. Pure and
 * clock-free — `todayIso` decides which week is current (never in the
 * ledger: the standing carries it) and which term is still planned.
 *
 * The copy is the mockup's (docs/project-page-mockup.html): "From Mon Aug 3,
 * 2026 · Part time 80% of 42 h = 33.6 h/wk" over "was 60% · 25.2 h · “note”",
 * "·· 3 weeks away · Jul 6 – 26 · vacation ··".
 */

import { addIsoDays, mondayOfIso } from "@/shared/lib";
import { formatHours, formatSignedHours, sortTerms, termHoursPerWeek, toPercent } from "./contract";
import type { Contract, ContractTerm, Ledger, LedgerNote, LedgerWeek, ProjectKind } from "./types";
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

export interface QuietRow {
	type: "quiet";
	text: string;
	/** The folded weeks, newest first. */
	weeks: LedgerWeek[];
}

export type LedgerRow = LedgerWeekRow | RuleRow | QuietRow;

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

/** Every rule the contract puts in the ledger, dated; placement is decided below. */
function contractRules(
	contract: Contract,
	ledger: Ledger,
	weeks: LedgerWeek[],
	todayIso: string,
): RuleRow[] {
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
		const endWeek = weeks.find((w) => w.weekOf <= endedOn && endedOn <= sundayOf(w.weekOf));
		const final = ledger.totals?.balance ?? endWeek?.balanceEnd ?? null;
		const finalText = final !== null ? ` · final balance ${formatSignedHours(final)}` : "";
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

/**
 * A week's +/−: the move between its close and the one before when both are
 * in the ledger; on the contract's first close — the week holding `since`, or
 * the week after when the one holding it has no close (a weekend start) — the
 * move from the opening balance. The balance counts only the contract's days,
 * so on those weeks worked − expected is not what moved it. Else worked −
 * expected, else worked − goal; null with neither, and for a week the ledger
 * does not hold. `openingBalance` is the contract's; null off a contract.
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
		if (older && older.balanceEnd !== null) return roundHours(week.balanceEnd - older.balanceEnd);
		const startWeek = ledger.since === null ? null : mondayOfIso(ledger.since);
		const firstClose = startWeek === weekOf || (older !== undefined && startWeek === older.weekOf);
		if (openingBalance !== null && firstClose) {
			return roundHours(week.balanceEnd - openingBalance);
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
 * the contract ended in. A rule dated in the current week or later sits at
 * the top, a ghost when it is still to come. A rule older than the oldest
 * week shown is not shown: the ledger has not reached it yet.
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
	const rules = contract ? contractRules(contract, ledger, weeks, todayIso) : [];
	const weekOfRule = (rule: RuleRow) => mondayOfIso(rule.date);

	const rows: LedgerRow[] = [];
	// Rules from the current week on, newest first, above everything.
	rows.push(
		...rules
			.filter((r) => weekOfRule(r) >= thisMonday)
			.sort((a, b) => b.date.localeCompare(a.date)),
	);
	const opening = contract ? contract.openingBalanceHours : null;
	for (const week of weeks) {
		const inWeek = rules.filter((r) => weekOfRule(r) === week.weekOf);
		rows.push(...inWeek.filter((r) => r.rule === "ended"));
		rows.push(weekRow(week, weekDelta(ledger, week.weekOf, opening)));
		rows.push(
			...inWeek.filter((r) => r.rule !== "ended").sort((a, b) => b.date.localeCompare(a.date)),
		);
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
 * text in the first cell.
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
		} else {
			const text = row.type === "rule" && row.sub ? `${row.text} · ${row.sub}` : row.text;
			lines.push(`${csvCell(text)},,,,`);
		}
	}
	return `${lines.join("\n")}\n`;
}
