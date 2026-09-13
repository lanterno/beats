/**
 * The standing: what the open week makes of the balance, in figures and in
 * one sentence (docs/project-page-roadmap.md, "The arithmetic"). Pure and
 * clock-free — `todayIso` is an argument — so every branch is a plain
 * function of a week and a day, and a branch that does not match gives null:
 * the page then shows the figures and no sentence, never a guessed one.
 *
 * Every figure is rounded as the balance is shown (one decimal, through
 * `balanceTone`), so a remaining of −0.04 h reads as met and a projection
 * never disagrees with the balance on a sign.
 */

import { addIsoDays, mondayOfIso } from "@/shared/lib";
import { balanceTone, sortTerms, termHoursPerDay, termHoursPerWeek } from "./contract";
import type { Contract, ContractDay, ContractTerm, ContractWeek, ProjectKind } from "./types";
import {
	hours1,
	isoWeek,
	isWeekday,
	nameDays,
	sundayOf,
	weekdayLong,
	weekdayShort,
} from "./weekDates";

export { weekNumber, weekRange } from "./weekDates";

/** "This week" for the week `todayIso` is in, else "Week 36" (ISO week number). */
export function weekLabel(weekOf: string, todayIso: string): string {
	if (weekOf === mondayOfIso(todayIso)) return "This week";
	return `Week ${isoWeek(weekOf)}`;
}

/**
 * The first seven days under the contract (Decision 2): the balance is
 * charged a day at a time and has not had a full week to settle, so the page
 * shows it muted with the first-week line. False before the contract starts
 * — that is another state — and without a term.
 */
export function isFirstWeek(contract: Contract, todayIso: string): boolean {
	const first = sortTerms(contract.terms)[0];
	if (!first) return false;
	return first.effectiveFrom <= todayIso && todayIso < addIsoDays(first.effectiveFrom, 7);
}

/** Two decimals, as the API rounds every hour figure, so float noise never reaches a sign. */
function roundHours(hours: number): number {
	return Math.round(hours * 100) / 100;
}

function inWeek(weekOf: string, todayIso: string): boolean {
	return todayIso >= weekOf && todayIso <= sundayOf(weekOf);
}

export interface Projection {
	/** The balance on Monday morning if no more hours are worked this week. */
	stopNow: number;
	/** The balance on Monday morning if the week's expectation is met. */
	met: number;
}

/**
 * "By Sunday: +5.7 h if the week is met, +3.8 h if you stop now" (Decision 3).
 * `stopNow` charges every day from today through Sunday against today's
 * balance — today's hours already count, today's expectation is charged as
 * the day closes; `met` adds what is still to go. Null without a balance or
 * an expectation, and when `todayIso` is not in the week: the balance is
 * pinned to today whatever week is open, so only the current week projects.
 */
export function projection(week: ContractWeek, todayIso: string): Projection | null {
	if (week.balance === undefined || week.expected === undefined) return null;
	if (!inWeek(week.weekOf, todayIso)) return null;
	const ahead = week.days.filter((d) => d.date >= todayIso).reduce((sum, d) => sum + d.expected, 0);
	const stopNow = week.balance - ahead;
	const remaining = week.remaining ?? week.expected - week.worked;
	return { stopNow: roundHours(stopNow), met: roundHours(stopNow + Math.max(remaining, 0)) };
}

/** "vacation", "sick", "other", or the holiday's name — why a day owed less; undefined otherwise. */
function dayOffReason(day: ContractDay): string | undefined {
	if (day.holiday) return day.holiday;
	if (day.absence) return day.absence.type;
	return undefined;
}

/**
 * "33.6 h nominal − Fri vacation 6.7 h": the term's hours and what each
 * holiday and absence took off them, only when the week expects less than
 * the term says (a half day takes half). Null when they agree, when there is
 * no expectation, and when the named days do not account for the whole
 * difference (a term change or the contract's first or last day mid-week —
 * the ledger's rule row says so there).
 */
export function nominalLine(week: ContractWeek, term: ContractTerm): string | null {
	const nominal = termHoursPerWeek(term);
	if (nominal == null || week.expected === undefined) return null;
	if (Math.abs(week.expected - nominal) < 0.005) return null;
	const perDay = termHoursPerDay(term) ?? 0;
	const deductions: string[] = [];
	let cuts = 0;
	for (const day of week.days) {
		if (!isWeekday(day.date)) continue;
		const reason = dayOffReason(day);
		if (!reason) continue;
		const cut = roundHours(perDay - day.expected);
		if (cut < 0.005) continue;
		cuts += cut;
		deductions.push(`${weekdayShort(day.date)} ${reason} ${hours1(cut)}`);
	}
	if (deductions.length === 0) return null;
	// The named days must account for the whole difference: a term change
	// mid-week moves the per-day hours, and a line that does not add up to
	// Expected is worse than none.
	if (Math.abs(nominal - cuts - week.expected) > 0.05) return null;
	return `${hours1(nominal)} nominal − ${deductions.join(" − ")}`;
}

/**
 * The week the standing speaks about. A `ContractWeek` fits; on a project
 * the contract does not govern the page passes the ledger's worked figure
 * and the goal, and there are no days to read.
 */
export interface StandingWeek {
	weekOf: string;
	worked: number;
	expected?: number;
	remaining?: number;
	days?: ContractDay[];
}

export interface WeekSentenceInput {
	week: StandingWeek;
	/** The following week against the contract, for "then Mon 6.7 h". */
	nextWeek?: ContractWeek | null;
	todayIso: string;
	kind: ProjectKind;
	/** The personal goal in force, where the contract does not govern; null for "no goal". */
	personalGoal?: number | null;
	goalType?: "target" | "cap";
}

/** "The week is met." / "The week is done — 0.4 h over."; null while hours are still to go. */
function doneSentence(remaining: number): string | null {
	const over = -remaining;
	const tone = balanceTone(over);
	if (tone === "owed") return null;
	if (tone === "even") return "The week is met.";
	return `The week is done — ${hours1(Number(over.toFixed(1)))} over.`;
}

/** "about 6.2 h a day" / "about 50 min a day", to the five minutes under an hour. */
function perDay(hours: number): string {
	if (hours >= 1) return hours1(Number(hours.toFixed(1)));
	const minutes = Math.max(5, Math.round((hours * 60) / 5) * 5);
	return `${minutes} min`;
}

function capitalise(word: string): string {
	return word.charAt(0).toUpperCase() + word.slice(1);
}

function contractSentence(
	week: StandingWeek,
	expected: number,
	nextWeek: ContractWeek | null | undefined,
	todayIso: string,
): string | null {
	const remaining = week.remaining ?? expected - week.worked;
	const done = doneSentence(remaining);
	if (done) return done;
	const days = week.days ?? [];
	const today = days.find((d) => d.date === todayIso);
	const todayExpected = today?.expected ?? 0;
	const later = days.filter((d) => d.date > todayIso && d.expected > 0);
	const toGo = `${hours1(remaining)} to go`;

	if (later.length === 0) {
		if (todayExpected === 0) return `The week closes ${hours1(remaining)} short.`;
		// "1.9 h to go, all today. Friday is off, then Mon 6.7 h."
		const off = days.filter(
			(d) => d.date > todayIso && isWeekday(d.date) && d.expected === 0 && dayOffReason(d),
		);
		const offText =
			off.length > 0
				? `${nameDays(
						off.map((d) => d.date),
						weekdayLong,
					)} ${off.length === 1 ? "is" : "are"} off`
				: null;
		const next = nextWeek?.days.find((d) => d.expected > 0);
		const nextText = next ? `then ${weekdayShort(next.date)} ${hours1(next.expected)}` : null;
		const base = `${toGo}, all today.`;
		if (offText && nextText) return `${base} ${offText}, ${nextText}.`;
		if (offText) return `${base} ${offText}.`;
		if (nextText) return `${base} ${capitalise(nextText)}.`;
		return base;
	}

	const lead =
		todayExpected > 0
			? ""
			: `Nothing due today${today && dayOffReason(today) ? ` (${capitalise(dayOffReason(today) ?? "")})` : ""}. `;
	const due = todayExpected > 0 && today ? [today, ...later] : later;
	if (due.length === 1) return `${lead}${toGo} on ${weekdayLong(due[0].date)}.`;
	const spread = `about ${perDay(remaining / due.length)} a day`;
	return `${lead}${toGo} over ${nameDays(due.map((d) => d.date))} — ${spread}.`;
}

function goalSentence(
	week: StandingWeek,
	todayIso: string,
	goal: number | null | undefined,
	goalType: "target" | "cap",
): string | null {
	// A cap has nothing "to go"; the label reads "Under cap" and says it.
	if (goal == null || goalType === "cap") return null;
	const remaining = goal - week.worked;
	const done = doneSentence(remaining);
	if (done) return done;
	const sunday = sundayOf(week.weekOf);
	const left: string[] = [];
	for (let d = todayIso; d <= sunday; d = addIsoDays(d, 1)) left.push(d);
	const toGo = `${hours1(remaining)} to go`;
	if (left.length === 1) return `${toGo}, all today.`;
	return `${toGo} over ${nameDays(left)} — about ${perDay(remaining / left.length)} a day.`;
}

/**
 * The one sentence under the week's figures, or null when no branch matches.
 * On a day job with an expectation the week runs against the contract:
 * met · all today (with the days off and next week's first day) · nothing
 * due today · N days with about-per-day · closes short. Anywhere else —
 * another kind, an objective term, before the first term — it runs against
 * the personal goal over the calendar days left. Null outside the week:
 * a past week open shows "closed" and no sentence.
 */
export function weekSentence(input: WeekSentenceInput): string | null {
	const { week, todayIso, kind } = input;
	if (!inWeek(week.weekOf, todayIso)) return null;
	if (kind === "day_job" && week.expected !== undefined) {
		return contractSentence(week, week.expected, input.nextWeek, todayIso);
	}
	return goalSentence(week, todayIso, input.personalGoal, input.goalType ?? "target");
}
