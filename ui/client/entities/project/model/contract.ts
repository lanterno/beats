/**
 * Contract arithmetic the UI needs before the API answers: which term a day
 * falls under, what a term owes a week, and how to say so. The API owns the
 * expectation and the balance (docs/work-contracts-roadmap.md); this is only
 * enough to label a term and to know whether the contract is time-based
 * today, which decides whether the personal goal is shown.
 */

import type { Contract, ContractTerm, ScheduleType } from "./types";

const WORKDAYS_PER_WEEK = 5;

export const SCHEDULE_TYPE_LABELS: Record<ScheduleType, string> = {
	full_time: "Full time",
	part_time: "Part time",
	custom: "Custom",
	objective: "Objective",
};

/** Whether a term owes hours at all — false only for an objective term. */
export function isTimeBased(scheduleType: ScheduleType): boolean {
	return scheduleType !== "objective";
}

/**
 * Hours the week owes under a term; null for an objective term, and for a
 * time-based term missing its numbers (the API would have refused it).
 */
export function termHoursPerWeek(term: ContractTerm): number | null {
	if (term.scheduleType === "objective") return null;
	if (term.scheduleType === "custom") return term.weeklyHours ?? null;
	if (term.fullTimeHours == null || term.percentage == null) return null;
	// Round away the float noise of 42 × 0.8 so the label reads 33.6, not 33.600000000000001.
	return Math.round(term.fullTimeHours * term.percentage * 100) / 100;
}

/** What one weekday owes under a term, and what a day off costs. */
export function termHoursPerDay(term: ContractTerm): number | null {
	const weekly = termHoursPerWeek(term);
	return weekly == null ? null : Math.round((weekly / WORKDAYS_PER_WEEK) * 100) / 100;
}

/**
 * The term in force on a day: the one with the latest effectiveFrom on or
 * before it. Undefined before the first term starts. Terms are kept sorted
 * by the API, but a contract under edit may not be, so this does not rely
 * on order.
 */
export function termOn(contract: Contract, isoDate: string): ContractTerm | undefined {
	let found: ContractTerm | undefined;
	for (const term of contract.terms) {
		if (term.effectiveFrom <= isoDate && (!found || term.effectiveFrom > found.effectiveFrom)) {
			found = term;
		}
	}
	return found;
}

/**
 * Whether the contract, not the personal goal, is a week's goal: the project
 * is a day job whose term in force on the week's Monday is time-based. This
 * is the API's `Project.goal_term` rule, and it decides what the API ignores
 * on such a week — the personal goal and every override — so the UI must not
 * offer to edit them there. Before the first term, under an objective term,
 * without a contract and on every other kind, the personal goal applies.
 *
 * Not the same question as `isTimeBasedOn`, which also counts a contract
 * that has not started yet, so a form can hide the goal a contract being
 * set up will replace.
 */
export function contractGovernsWeek(
	project: { kind: string; contract?: Contract },
	mondayIso: string,
): boolean {
	if (project.kind !== "day_job" || !project.contract) return false;
	const term = termOn(project.contract, mondayIso);
	return term !== undefined && isTimeBased(term.scheduleType);
}

/**
 * The term the UI should describe as "the contract" on a day: the one in
 * force, or — before the contract has started — the first one to come.
 */
export function displayTermOn(contract: Contract, isoDate: string): ContractTerm | undefined {
	return termOn(contract, isoDate) ?? sortTerms(contract.terms)[0];
}

/**
 * Whether the contract owes hours on a day — its term in force (or, before
 * it starts, the first to come) is time-based. False without a contract:
 * nothing but the personal goal applies then. Decides whether the goal is
 * shown, in the form and on the project page alike.
 */
export function isTimeBasedOn(contract: Contract | undefined, isoDate: string): boolean {
	const term = contract ? displayTermOn(contract, isoDate) : undefined;
	return term !== undefined && isTimeBased(term.scheduleType);
}

/** Terms in ascending order of effectiveFrom, as the API keeps them. */
export function sortTerms(terms: ContractTerm[]): ContractTerm[] {
	return [...terms].sort((a, b) => a.effectiveFrom.localeCompare(b.effectiveFrom));
}

/** A percentage stored as a fraction (0.8), shown as a percent (80). */
export function toPercent(fraction: number): number {
	return Math.round(fraction * 10000) / 100;
}

/** A percent as typed (80), sent as the fraction the API stores (0.8). */
export function fromPercent(percent: number): number {
	return Math.round(percent * 100) / 10000;
}

function formatHours(hours: number): string {
	return `${Math.round(hours * 100) / 100} h`;
}

/** Which way a balance leans, judged on the figure as shown (one decimal). */
export type BalanceTone = "over" | "owed" | "even";

/** A balance rounded to the decimal it is shown at, so tone and text agree at ±0.04. */
function roundedBalance(hours: number): number {
	return Number(hours.toFixed(1));
}

export function balanceTone(hours: number): BalanceTone {
	const rounded = roundedBalance(hours);
	if (rounded > 0) return "over";
	if (rounded < 0) return "owed";
	return "even";
}

/**
 * A balance with its sign made unmistakable: "+4.5 h over", "−2.0 h owed"
 * or "even" — never a bare signed number, whose minus is easy to miss.
 */
export function describeBalance(hours: number): string {
	const tone = balanceTone(hours);
	if (tone === "even") return "even";
	const magnitude = Math.abs(roundedBalance(hours)).toFixed(1);
	return tone === "over" ? `+${magnitude} h over` : `−${magnitude} h owed`;
}

/** The short form for a chip: "+4.5 h", "−2.0 h", or "even". */
export function formatSignedHours(hours: number): string {
	const tone = balanceTone(hours);
	if (tone === "even") return "even";
	const magnitude = Math.abs(roundedBalance(hours)).toFixed(1);
	return tone === "over" ? `+${magnitude} h` : `−${magnitude} h`;
}

/**
 * One line for a term: "Part time · 80% of 42 h · 33.6 h/week". Objective
 * terms have no numbers to show.
 */
export function describeTerm(term: ContractTerm): string {
	const label = SCHEDULE_TYPE_LABELS[term.scheduleType];
	const weekly = termHoursPerWeek(term);
	switch (term.scheduleType) {
		case "objective":
			return `${label} · no weekly expectation`;
		case "custom":
			return weekly == null ? label : `${label} · ${formatHours(weekly)}/week`;
		case "full_time":
			return weekly == null ? label : `${label} · ${formatHours(weekly)}/week`;
		case "part_time": {
			if (weekly == null || term.fullTimeHours == null || term.percentage == null) return label;
			const pct = toPercent(term.percentage);
			return `${label} · ${pct}% of ${formatHours(term.fullTimeHours)} · ${formatHours(weekly)}/week`;
		}
	}
}
