/**
 * The one time navigator (Decision 10): the open week, as `?week=YYYY-MM-DD`
 * in the URL. Absent, the current week. Any day of a week names its Monday;
 * a malformed value reads as the current week. Set to the current week the
 * param is dropped, so the address stays minimal, and every move replaces
 * the history entry — the back button is not the way to return to today.
 */

import { useCallback } from "react";
import { useSearchParams } from "react-router";
import { mondayOfIso, parseIsoDate } from "@/shared/lib";

export function useOpenWeek(todayIso: string): [string, (weekOf: string) => void] {
	const [params, setParams] = useSearchParams();
	const thisMonday = mondayOfIso(todayIso);
	const raw = params.get("week");
	const weekOf = raw && parseIsoDate(raw) ? mondayOfIso(raw) : thisMonday;

	const setWeekOf = useCallback(
		(next: string) => {
			setParams(
				(prev) => {
					const monday = mondayOfIso(next);
					if (monday === thisMonday) prev.delete("week");
					else prev.set("week", monday);
					return prev;
				},
				{ replace: true },
			);
		},
		[setParams, thisMonday],
	);

	return [weekOf, setWeekOf];
}
