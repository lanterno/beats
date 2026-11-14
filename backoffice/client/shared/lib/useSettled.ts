/**
 * A value as it stands once typing has stopped.
 *
 * The review page previews the arguments it has, and the preview is a
 * request: without this, every keystroke in a reason field would be a POST
 * to the operator API, most of them answering 422 about a half-typed word.
 */

import { useEffect, useState } from "react";

/** The default pause: long enough to cover typing, short enough that the
 * page does not feel like it is lagging behind the field. */
export const SETTLE_MS = 400;

export function useSettled<T>(value: T, ms: number = SETTLE_MS): T {
	const [settled, setSettled] = useState(value);
	// JSON rather than the value itself: the callers pass a fresh object
	// each render, which would never compare equal.
	const key = JSON.stringify(value);

	// `key` stands in for `value` in the dependencies on purpose: callers
	// pass a fresh object each render, so depending on it directly would
	// restart the timer forever and never settle.
	// biome-ignore lint/correctness/useExhaustiveDependencies: key stands in for value, as above
	useEffect(() => {
		const timer = setTimeout(() => setSettled(value), ms);
		return () => clearTimeout(timer);
	}, [key, ms]);

	return settled;
}
