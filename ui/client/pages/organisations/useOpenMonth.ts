/**
 * A record page's month, as `?month=YYYY-MM` in the URL, the way the
 * Clients page holds its month. Absent, the current month; a malformed
 * value, or a month that has not started, reads as the current month too.
 * Set to the current month the param is dropped, and every move replaces
 * the history entry.
 */

import { useCallback } from "react";
import { useSearchParams } from "react-router";
import { isFutureMonth, monthOf } from "@/entities/billing";

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;

export function useOpenMonth(todayIso: string): [string, (month: string) => void] {
	const [params, setParams] = useSearchParams();
	const current = monthOf(todayIso);
	const raw = params.get("month");
	const month = raw && MONTH.test(raw) && !isFutureMonth(raw, todayIso) ? raw : current;

	const setMonth = useCallback(
		(next: string) => {
			setParams(
				(prev) => {
					if (next === current) prev.delete("month");
					else prev.set("month", next);
					return prev;
				},
				{ replace: true },
			);
		},
		[setParams, current],
	);

	return [month, setMonth];
}
