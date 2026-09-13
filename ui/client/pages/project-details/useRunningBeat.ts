/**
 * The running timer, when it runs on this project: the page's "→ now" row
 * and the live dot beside Worked. Subscribes with the timer's own query key
 * so the sidebar's refetch is the page's too — no second poll — and ticks a
 * clock so the live row's duration moves between refetches.
 */

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { fetchTimerStatus, timerStatusKey } from "@/features/timer";

export interface RunningBeat {
	/** When it started, as the API reports it (UTC ISO). */
	since: string;
}

export function useRunningBeat(projectId: string | undefined): RunningBeat | null {
	const { data } = useQuery({ queryKey: timerStatusKey, queryFn: fetchTimerStatus });
	if (!projectId || !data?.isBeating || !data.since) return null;
	if (data.project?.id !== projectId) return null;
	return { since: data.since };
}

/** The wall clock, re-read every `everyMs`; for a duration that counts up. */
export function useNow(everyMs = 30_000): number {
	const [now, setNow] = useState(() => Date.now());
	useEffect(() => {
		const id = setInterval(() => setNow(Date.now()), everyMs);
		return () => clearInterval(id);
	}, [everyMs]);
	return now;
}
