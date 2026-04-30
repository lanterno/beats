/**
 * Read/write a single URL search param as React state.
 *
 * Returns the same shape as `useState<string | undefined>`. Setting to
 * `undefined` (or empty string) deletes the param from the URL so the
 * search string stays minimal. Updates use `replaceState` (no history
 * entry per click) — the back button shouldn't be the way to clear a
 * filter, the user has the dismiss pill for that.
 *
 * Why not pull react-router's `useSearchParams`: this hook works in any
 * component (including ones rendered outside a Router context, e.g. in
 * Vitest specs) and gives us the exact `[value, setValue]` shape we
 * already use elsewhere. It does subscribe to history events so two
 * components reading the same param stay in sync.
 */
import { useCallback, useEffect, useState } from "react";

function readParam(key: string): string | undefined {
	if (typeof window === "undefined") return undefined;
	const v = new URLSearchParams(window.location.search).get(key);
	return v ?? undefined;
}

export function useUrlParam(
	key: string,
): [string | undefined, (value: string | undefined) => void] {
	const [value, setValue] = useState<string | undefined>(() => readParam(key));

	useEffect(() => {
		// Sync when the URL changes via back/forward or another hook on the
		// same key. We DON'T listen for "pushstate" — that fires on our own
		// writes too and would create a feedback loop.
		const onPop = () => setValue(readParam(key));
		window.addEventListener("popstate", onPop);
		return () => window.removeEventListener("popstate", onPop);
	}, [key]);

	const update = useCallback(
		(next: string | undefined) => {
			setValue(next);
			const params = new URLSearchParams(window.location.search);
			if (next === undefined || next === "") {
				params.delete(key);
			} else {
				params.set(key, next);
			}
			const search = params.toString();
			const url = `${window.location.pathname}${search ? `?${search}` : ""}${window.location.hash}`;
			window.history.replaceState({}, "", url);
		},
		[key],
	);

	return [value, update];
}
