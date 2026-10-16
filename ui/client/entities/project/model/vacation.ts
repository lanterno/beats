/**
 * The vacation entitlement in words (docs/work-contracts.md, Decision 14).
 * Pure and clock-free: every figure is the API's or the contract's, and
 * this only says them. Days are counted in halves (`halfDays`), which
 * formats a count, not a signed figure — so a negative one is said by its
 * size, with the sign in words ("overdrawn", "over"), never as "−3½".
 */

import { halfDays } from "./standing";
import type { VacationEntitlement } from "./types";

/** "Vacation 25 d/yr · up to 5 d carry over" — the register's constant. */
export function describeEntitlement(vacation: VacationEntitlement): string {
	const rule =
		vacation.carryOver === "all"
			? "all carry over"
			: vacation.carryOver === "none"
				? "unused lapse"
				: `up to ${halfDays(vacation.carryOverMaxDays ?? 0)} d carry over`;
	return `Vacation ${halfDays(vacation.daysPerYear)} d/yr · ${rule}`;
}
