/**
 * The wall clock as state, re-read every `everyMs`, so whatever reads it
 * renders again as time passes: a duration that counts up, a sentence
 * about an instant that may have passed. With `enabled` false nothing
 * ticks, and the clock is re-read once it turns true again.
 */

import { useEffect, useState } from "react";

/** The wall clock, re-read every `everyMs`; for a duration that counts up. */
export function useNow(everyMs = 30_000, { enabled = true }: { enabled?: boolean } = {}): number {
	const [now, setNow] = useState(() => Date.now());
	useEffect(() => {
		if (!enabled) return;
		setNow(Date.now());
		const id = setInterval(() => setNow(Date.now()), everyMs);
		return () => clearInterval(id);
	}, [everyMs, enabled]);
	return now;
}
