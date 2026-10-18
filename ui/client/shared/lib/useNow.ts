/**
 * The wall clock as state, re-read every `everyMs`, so whatever reads it
 * renders again as time passes: a duration that counts up, a sentence
 * about an instant that may have passed.
 */

import { useEffect, useState } from "react";

/** The wall clock, re-read every `everyMs`; for a duration that counts up. */
export function useNow(everyMs = 30_000): number {
	const [now, setNow] = useState(() => Date.now());
	useEffect(() => {
		const id = setInterval(() => setNow(Date.now()), everyMs);
		return () => clearInterval(id);
	}, [everyMs]);
	return now;
}
