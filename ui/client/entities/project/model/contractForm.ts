/**
 * The contract as a form holds it — strings in inputs — and the way across
 * to the domain shape. Validation here mirrors the API's term rules so the
 * usual mistakes are caught before a round-trip; the API stays the
 * authority, and its 422 lands on the same field keys (see
 * `contractFieldErrors`).
 */

import { parseIsoDate, todayIso } from "@/shared/lib";
import { fromPercent, sortTerms, toPercent } from "./contract";
import type { Contract, ContractTerm, ScheduleType } from "./types";

/** One term as its inputs hold it. Percentage is a percent here (80), a fraction on the wire. */
export interface TermFormValues {
	effectiveFrom: string;
	scheduleType: ScheduleType;
	fullTimeHours: string;
	percentage: string;
	weeklyHours: string;
	note: string;
}

export type TermFieldErrors = Partial<Record<keyof TermFormValues, string>>;

/** The contract's frame — everything but the terms, which have their own editor. */
export interface ContractFrameValues {
	holidayCountry: string;
	holidaySubdivision: string;
	openingBalanceHours: string;
	endedOn: string;
}

export type ContractFrameErrors = Partial<Record<keyof ContractFrameValues, string>>;

export function termFormDefaults(
	term?: ContractTerm,
	overrides: Partial<TermFormValues> = {},
): TermFormValues {
	return {
		effectiveFrom: term?.effectiveFrom ?? todayIso(),
		scheduleType: term?.scheduleType ?? "full_time",
		fullTimeHours: term?.fullTimeHours != null ? String(term.fullTimeHours) : "",
		percentage: term?.percentage != null ? String(toPercent(term.percentage)) : "",
		weeklyHours: term?.weeklyHours != null ? String(term.weeklyHours) : "",
		note: term?.note ?? "",
		...overrides,
	};
}

export function contractFrameDefaults(contract?: Contract): ContractFrameValues {
	return {
		holidayCountry: contract?.holidayCountry ?? "",
		holidaySubdivision: contract?.holidaySubdivision ?? "",
		openingBalanceHours:
			contract && contract.openingBalanceHours !== 0 ? String(contract.openingBalanceHours) : "",
		endedOn: contract?.endedOn ?? "",
	};
}

function numberOrNaN(raw: string): number {
	return raw.trim() === "" ? Number.NaN : Number(raw);
}

/** The API's per-term rules, as the form can check them before sending. */
export function validateTerm(values: TermFormValues): TermFieldErrors {
	const errors: TermFieldErrors = {};
	if (!parseIsoDate(values.effectiveFrom)) {
		errors.effectiveFrom = "Enter the day this term starts";
	}
	switch (values.scheduleType) {
		case "objective":
			break;
		case "custom": {
			const weekly = numberOrNaN(values.weeklyHours);
			if (Number.isNaN(weekly) || weekly < 0) {
				errors.weeklyHours = "Enter the hours per week (0 or more)";
			}
			break;
		}
		case "full_time":
		case "part_time": {
			const basis = numberOrNaN(values.fullTimeHours);
			if (Number.isNaN(basis) || basis <= 0) {
				errors.fullTimeHours = "Enter what a full-time week is, in hours";
			}
			if (values.scheduleType === "part_time") {
				// Judge what reaches the wire: fromPercent rounds to four decimals,
				// so 99.999 arrives as 1 (full time) and 0.001 as 0 — both refused.
				const fraction = fromPercent(numberOrNaN(values.percentage));
				if (Number.isNaN(fraction) || fraction <= 0 || fraction >= 1) {
					errors.percentage = "Enter a percentage above 0 and below 100";
				}
			}
			break;
		}
	}
	return errors;
}

/** Form → domain. Call validateTerm first; this trusts the numbers. */
export function termFromForm(values: TermFormValues): ContractTerm {
	const term: ContractTerm = {
		effectiveFrom: values.effectiveFrom,
		scheduleType: values.scheduleType,
	};
	const note = values.note.trim();
	if (note) term.note = note;
	switch (values.scheduleType) {
		case "objective":
			break;
		case "custom":
			term.weeklyHours = Number(values.weeklyHours);
			break;
		case "full_time":
			term.fullTimeHours = Number(values.fullTimeHours);
			term.percentage = 1;
			break;
		case "part_time":
			term.fullTimeHours = Number(values.fullTimeHours);
			term.percentage = fromPercent(Number(values.percentage));
			break;
	}
	return term;
}

export function validateContractFrame(
	values: ContractFrameValues,
	firstTermStarts: string | undefined,
): ContractFrameErrors {
	const errors: ContractFrameErrors = {};
	if (
		values.openingBalanceHours.trim() !== "" &&
		Number.isNaN(Number(values.openingBalanceHours))
	) {
		errors.openingBalanceHours = "Enter a number of hours (negative if owed)";
	}
	if (values.endedOn.trim() !== "") {
		if (!parseIsoDate(values.endedOn)) {
			errors.endedOn = "Enter a date";
		} else if (firstTermStarts && values.endedOn < firstTermStarts) {
			errors.endedOn = "The contract cannot end before its first term starts";
		}
	}
	return errors;
}

/**
 * Form → domain for the whole contract. `terms` are whatever the caller
 * holds — the existing history when editing the frame, the one new term
 * when creating — sorted the way the API wants them.
 */
export function contractFromForm(frame: ContractFrameValues, terms: ContractTerm[]): Contract {
	const contract: Contract = {
		terms: sortTerms(terms),
		openingBalanceHours:
			frame.openingBalanceHours.trim() === "" ? 0 : Number(frame.openingBalanceHours),
	};
	const country = frame.holidayCountry.trim();
	if (country) {
		contract.holidayCountry = country;
		const subdivision = frame.holidaySubdivision.trim();
		if (subdivision) contract.holidaySubdivision = subdivision;
	}
	const endedOn = frame.endedOn.trim();
	if (endedOn) contract.endedOn = endedOn;
	return contract;
}

const TERM_LEAVES: Record<string, keyof TermFormValues> = {
	effective_from: "effectiveFrom",
	schedule_type: "scheduleType",
	full_time_hours: "fullTimeHours",
	percentage: "percentage",
	weekly_hours: "weeklyHours",
	note: "note",
};

const FRAME_LEAVES: Record<string, keyof ContractFrameValues> = {
	holiday_country: "holidayCountry",
	holiday_subdivision: "holidaySubdivision",
	opening_balance_hours: "openingBalanceHours",
	ended_on: "endedOn",
};

export interface ContractFieldErrors {
	term: TermFieldErrors;
	frame: ContractFrameErrors;
	/** Messages about the contract as a whole (terms out of order, no terms) or an unmapped path. */
	general: string[];
}

/**
 * Sort a 422's `fields` (path → message) into the contract's inputs. `prefix`
 * is where the contract sits in the request — "contract" on the project
 * routes, "" on PUT /contract — and `termIndex` which term's errors belong to
 * the editor on screen; the others become general messages. Paths outside
 * the contract are left for the caller.
 */
export function contractFieldErrors(
	fields: Record<string, string>,
	prefix: string,
	termIndex: number,
): ContractFieldErrors {
	const out: ContractFieldErrors = { term: {}, frame: {}, general: [] };
	for (const [path, message] of Object.entries(fields)) {
		if (prefix && path !== prefix && !path.startsWith(`${prefix}.`)) continue;
		const inner = prefix ? path.slice(prefix.length + 1) : path;
		const parts = inner === "" ? [] : inner.split(".");
		if (parts.length === 0 || parts[0] === "terms") {
			const index = parts.length >= 2 ? Number(parts[1]) : Number.NaN;
			const leaf = parts.length >= 3 ? TERM_LEAVES[parts[2]] : undefined;
			if (index === termIndex && leaf) {
				out.term[leaf] = message;
			} else if (index === termIndex && parts.length === 2) {
				// A term-level validator (the numbers do not fit the schedule type).
				out.term.scheduleType = message;
			} else {
				out.general.push(message);
			}
			continue;
		}
		const frameLeaf = FRAME_LEAVES[parts[0]];
		if (frameLeaf) out.frame[frameLeaf] = message;
		else out.general.push(message);
	}
	return out;
}
