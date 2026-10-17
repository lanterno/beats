/**
 * The contract as a form holds it — strings in inputs — and the way across
 * to the domain shape. Validation here mirrors the API's term rules so the
 * usual mistakes are caught before a round-trip; the API stays the
 * authority, and its 422 lands on the same field keys (see
 * `contractFieldErrors`).
 */

import { parseIsoDate, todayIso } from "@/shared/lib";
import { fromPercent, sortTerms, toPercent } from "./contract";
import type { CarryOver, Contract, ContractTerm, ScheduleType, VacationEntitlement } from "./types";

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

/**
 * The contract's frame — everything but the terms, which have their own
 * editor. The `vacation…` fields are the entitlement: an empty days per
 * year means none is tracked, and the rest are then ignored. The carry-over
 * starts unchosen, and neither opening field is prefilled: each is a figure
 * off the contract or an HR statement, not a guess.
 */
export interface ContractFrameValues {
	holidayCountry: string;
	holidaySubdivision: string;
	openingBalanceHours: string;
	endedOn: string;
	vacationDaysPerYear: string;
	vacationCarryOver: CarryOver | "";
	vacationCarryOverMax: string;
	vacationOpeningOn: string;
	vacationOpeningDays: string;
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
		...vacationFrameDefaults(contract?.vacation),
	};
}

function vacationFrameDefaults(
	vacation: VacationEntitlement | undefined,
): Pick<
	ContractFrameValues,
	| "vacationDaysPerYear"
	| "vacationCarryOver"
	| "vacationCarryOverMax"
	| "vacationOpeningOn"
	| "vacationOpeningDays"
> {
	return {
		vacationDaysPerYear: vacation ? String(vacation.daysPerYear) : "",
		vacationCarryOver: vacation?.carryOver ?? "",
		vacationCarryOverMax:
			vacation?.carryOverMaxDays != null ? String(vacation.carryOverMaxDays) : "",
		vacationOpeningOn: vacation?.openingOn ?? "",
		vacationOpeningDays: vacation ? String(vacation.openingDays) : "",
	};
}

/** Whether `n` is a whole or half number — what every vacation figure must be. */
function isHalves(n: number): boolean {
	return Number.isFinite(n) && Number.isInteger(n * 2);
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
	if (values.vacationDaysPerYear.trim() !== "") {
		validateVacation(values, firstTermStarts, errors);
	}
	return errors;
}

/** The entitlement's rules, as the API states them, when days per year are given. */
function validateVacation(
	values: ContractFrameValues,
	firstTermStarts: string | undefined,
	errors: ContractFrameErrors,
): void {
	const days = Number(values.vacationDaysPerYear);
	if (!isHalves(days) || days <= 0 || days > 366) {
		errors.vacationDaysPerYear = "Enter the days per year, in whole or half days";
	}
	if (values.vacationCarryOver === "") {
		errors.vacationCarryOver = "Choose what happens to unused days";
	} else if (values.vacationCarryOver === "capped") {
		const cap = numberOrNaN(values.vacationCarryOverMax);
		if (!isHalves(cap) || cap <= 0 || cap > 366) {
			errors.vacationCarryOverMax = "Enter how many days carry over, in whole or half days";
		}
	}
	const openingOn = values.vacationOpeningOn.trim();
	const endedOn = values.endedOn.trim();
	if (!parseIsoDate(openingOn)) {
		errors.vacationOpeningOn = "Enter the day counting starts";
	} else if (firstTermStarts && openingOn < firstTermStarts) {
		errors.vacationOpeningOn = "Counting cannot start before the contract does";
	} else if (endedOn && parseIsoDate(endedOn) && openingOn > endedOn) {
		errors.vacationOpeningOn = "Counting cannot start after the contract ends";
	}
	const opening = numberOrNaN(values.vacationOpeningDays);
	if (!isHalves(opening) || Math.abs(opening) > 366) {
		errors.vacationOpeningDays = "Enter the days left that morning (negative if overdrawn)";
	}
}

/** Form → domain for the entitlement; none when days per year are left empty. */
function vacationFromForm(frame: ContractFrameValues): VacationEntitlement | undefined {
	if (frame.vacationDaysPerYear.trim() === "" || frame.vacationCarryOver === "") return undefined;
	const vacation: VacationEntitlement = {
		daysPerYear: Number(frame.vacationDaysPerYear),
		carryOver: frame.vacationCarryOver,
		openingOn: frame.vacationOpeningOn.trim(),
		openingDays: Number(frame.vacationOpeningDays),
	};
	if (frame.vacationCarryOver === "capped") {
		vacation.carryOverMaxDays = Number(frame.vacationCarryOverMax);
	}
	return vacation;
}

/**
 * Form → domain for the whole contract. `terms` are whatever the caller
 * holds — the existing history when editing the frame, the one new term
 * when creating — sorted the way the API wants them. `kept` are the
 * holiday lists, edited only in the Holidays dialog: the existing
 * contract's, or empty ones on create, carried through unchanged. A region
 * change — "No region" included — clears neither: a date not given that the
 * new region does not have simply does nothing, and the marks a new region
 * would bring into force are cleared only when the user asks
 * (`revivedNotGiven`), by the caller, in `kept`. The vacation entitlement is
 * the frame's own: empty days per year leave it out, which the wire sends
 * as null and so clears it.
 */
export function contractFromForm(
	frame: ContractFrameValues,
	terms: ContractTerm[],
	kept: Pick<Contract, "companyHolidays" | "holidaysNotGiven">,
): Contract {
	const contract: Contract = {
		terms: sortTerms(terms),
		openingBalanceHours:
			frame.openingBalanceHours.trim() === "" ? 0 : Number(frame.openingBalanceHours),
		companyHolidays: kept.companyHolidays,
		holidaysNotGiven: kept.holidaysNotGiven,
	};
	const country = frame.holidayCountry.trim();
	if (country) {
		contract.holidayCountry = country;
		const subdivision = frame.holidaySubdivision.trim();
		if (subdivision) contract.holidaySubdivision = subdivision;
	}
	const endedOn = frame.endedOn.trim();
	if (endedOn) contract.endedOn = endedOn;
	const vacation = vacationFromForm(frame);
	if (vacation) contract.vacation = vacation;
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

const VACATION_LEAVES: Record<string, keyof ContractFrameValues> = {
	days_per_year: "vacationDaysPerYear",
	carry_over: "vacationCarryOver",
	carry_over_max_days: "vacationCarryOverMax",
	opening_on: "vacationOpeningOn",
	opening_days: "vacationOpeningDays",
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
		const frameLeaf =
			parts[0] === "vacation"
				? parts.length === 2
					? VACATION_LEAVES[parts[1]]
					: undefined
				: FRAME_LEAVES[parts[0]];
		if (frameLeaf) out.frame[frameLeaf] = message;
		else out.general.push(message);
	}
	return out;
}
