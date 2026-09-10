/**
 * What `shared/` and `entities/` need from a session, without knowing what a
 * session is.
 *
 * Both layers sit below `features/` and may not import from it. But the API
 * client has to attach a bearer token and drop the session when the server
 * rejects one, and browser storage has to be scoped per account so a shared
 * machine doesn't leak one person's state into another's. So the lower layers
 * declare the port, and `app/` — the one layer allowed to know about both
 * sides — wires the auth feature into it before the first render.
 *
 * Until that wiring runs the port behaves as a signed-out visitor, which is
 * what a caller reaching it that early would be anyway.
 */

import { useSyncExternalStore } from "react";

export interface SessionPort {
	getToken(): string | null;
	/** A stable per-account key for scoping browser storage. Null when signed out. */
	getUserKey(): string | null;
	/** Notify on any change to the above. Returns the unsubscribe. */
	subscribe(onChange: () => void): () => void;
	/** Drop local session state — the server has already rejected us. */
	clear(): void;
	/** Tell the server first, then drop local state. Never rejects. */
	signOut(): Promise<void>;
}

const signedOut: SessionPort = {
	getToken: () => null,
	getUserKey: () => null,
	subscribe: () => () => {},
	clear: () => {},
	signOut: async () => {},
};

let port: SessionPort = signedOut;

export function provideSession(impl: SessionPort): void {
	port = impl;
}

export function sessionToken(): string | null {
	return port.getToken();
}

export function endSession(): void {
	port.clear();
}

export function signOut(): Promise<void> {
	return port.signOut();
}

// Module-level so useSyncExternalStore sees stable references and doesn't
// resubscribe on every render.
const subscribe = (onChange: () => void) => port.subscribe(onChange);
const getUserKey = () => port.getUserKey();

/** The storage-scoping key for the signed-in account, or null. Reactive. */
export function useSessionUserKey(): string | null {
	return useSyncExternalStore(subscribe, getUserKey);
}
