/**
 * The account is suspended (403 ACCOUNT_SUSPENDED,
 * docs/account-controls.md), and the API said so in a sentence that names the address to write
 * to. This holds that sentence for the full-page notice in `app/App.tsx`.
 *
 * Recording it also ends the session, exactly as a sign-out would — a
 * suspended token buys nothing — but deliberately **without** the 401 path's
 * redirect home: the person must read why, not find themselves on the login
 * screen with no explanation and sign back in to a loop. The notice stays
 * until the page reloads; the sync engine stops its polling the moment it is
 * recorded (useSyncEngine subscribes here), and the write queue keeps every
 * pending write — a suspension can be undone, so nothing of the person's is
 * dropped (the API-side rule, and the companion's rule 7).
 */

import { useSyncExternalStore } from "react";
import { endSession } from "@/shared/session";

let notice: string | null = null;
const listeners = new Set<() => void>();

export function recordSuspension(detail: string): void {
	if (notice !== null) return; // the first refusal's wording stands
	notice = detail;
	for (const l of listeners) l();
	endSession();
}

export function suspensionNotice(): string | null {
	return notice;
}

export function subscribeSuspension(onChange: () => void): () => void {
	listeners.add(onChange);
	return () => {
		listeners.delete(onChange);
	};
}

/** The notice, reactively, for the full-page gate in App.tsx. */
export function useSuspensionNotice(): string | null {
	return useSyncExternalStore(subscribeSuspension, suspensionNotice);
}

/** Tests only: the store is module-level and must not leak between them. */
export function resetSuspensionForTests(): void {
	notice = null;
}
