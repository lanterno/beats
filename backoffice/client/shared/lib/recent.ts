/**
 * The accounts you opened recently, in this browser.
 *
 * Ids and the day you opened them, nothing else, and **never an address**:
 * an address must not reach a URL, browser history or a list like this one
 * (docs/backoffice.md § The line — Cloud Run logs every URL for 30 days).
 * The day is here because it is what expires an entry; it is not a record of
 * anything, it is in `localStorage` rather than the database, and nobody but
 * this operator on this machine can read it.
 *
 * Reads are not audited (docs/backoffice.md § Not decided), so this must
 * not grow into a log that says who looked at whom. If that decision is ever
 * taken, it belongs in the audit, not here.
 */

const KEY = "backoffice.recent-accounts";
/** After a week an entry drops: a convenience, never a history. */
export const RECENT_DAYS = 7;
/** Enough to get back to what you were doing, not a browsable list. */
export const RECENT_LIMIT = 8;

export interface Opened {
	id: string;
	/** The UTC day it was opened, `YYYY-MM-DD`. */
	day: string;
}

const dayOf = (at: Date): string => at.toISOString().slice(0, 10);

const daysBetween = (from: string, to: string): number =>
	Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);

/** Entries still inside the week, newest first. Anything malformed is dropped
 * rather than shown: this is a cache, and a bad row is not worth a failure. */
export function fresh(entries: unknown, today: Date): Opened[] {
	if (!Array.isArray(entries)) return [];
	const now = dayOf(today);
	return entries
		.filter(
			(e): e is Opened =>
				!!e &&
				typeof e === "object" &&
				typeof (e as Opened).id === "string" &&
				typeof (e as Opened).day === "string" &&
				/^\d{4}-\d{2}-\d{2}$/.test((e as Opened).day),
		)
		.filter((e) => {
			const age = daysBetween(e.day, now);
			// A day in the future is a clock that moved, not a fresh entry.
			return age >= 0 && age < RECENT_DAYS;
		})
		.slice(0, RECENT_LIMIT);
}

/** `id` on the front, with today's day, and no second copy of it. */
export function withOpened(entries: Opened[], id: string, today: Date): Opened[] {
	return [{ id, day: dayOf(today) }, ...entries.filter((e) => e.id !== id)].slice(0, RECENT_LIMIT);
}

export function readRecent(today = new Date()): Opened[] {
	try {
		return fresh(JSON.parse(localStorage.getItem(KEY) ?? "[]"), today);
	} catch {
		return [];
	}
}

export function rememberOpened(id: string, today = new Date()): void {
	try {
		localStorage.setItem(KEY, JSON.stringify(withOpened(readRecent(today), id, today)));
	} catch {
		// A browser with storage refused still shows every page.
	}
}
