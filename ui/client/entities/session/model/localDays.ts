/**
 * Sessions bucketed by the local calendar day each one started on — the
 * rule the API's `worked_by_local_day` applies, so a day row's sessions add
 * up to the ledger's figure for that day. A session that crosses midnight
 * belongs whole to the day it started; splitting it would put a figure on a
 * day no session row explains.
 */

import { addIsoDays, parseUtcIso, toIsoDate } from "@/shared/lib";
import type { Session } from "./types";

export interface LocalDaySessions {
	date: string; // YYYY-MM-DD
	/** In order of start. */
	sessions: Session[];
	totalMinutes: number;
	sessionCount: number;
}

/**
 * Seven entries, Monday to Sunday, for the week starting `mondayIso`; a
 * session outside the week is left out. Pure: the day is read off each
 * session's start in the browser's timezone.
 */
export function groupSessionsByLocalDay(
	sessions: Session[],
	mondayIso: string,
): LocalDaySessions[] {
	const days = Array.from({ length: 7 }, (_, i) => addIsoDays(mondayIso, i));
	const buckets = new Map<string, Session[]>(days.map((date) => [date, []]));
	for (const session of sessions) {
		buckets.get(toIsoDate(parseUtcIso(session.startTime)))?.push(session);
	}
	return days.map((date) => {
		const list = [...(buckets.get(date) ?? [])].sort(
			(a, b) => parseUtcIso(a.startTime).getTime() - parseUtcIso(b.startTime).getTime(),
		);
		return {
			date,
			sessions: list,
			totalMinutes: list.reduce((sum, s) => sum + s.duration, 0),
			sessionCount: list.length,
		};
	});
}
