/**
 * Wires the auth feature into the session port that `shared/` and `entities/`
 * read through. `app/` is the only layer allowed to import from both sides,
 * which is the whole reason the port exists — see `shared/session`.
 *
 * Called from `main.tsx` before the first render, so no component can observe
 * the signed-out default that the port starts with.
 */

import {
	clearSessionToken,
	getAuthUserKey,
	getSessionToken,
	logout,
	subscribeToAuth,
} from "@/features/auth";
import { provideSession } from "@/shared/session";

export function wireSession(): void {
	provideSession({
		getToken: getSessionToken,
		getUserKey: getAuthUserKey,
		subscribe: subscribeToAuth,
		clear: clearSessionToken,
		// The server call is best-effort: a failed revoke must not strand the
		// user in a session they asked to leave, so the local clear runs either
		// way and the caller is never handed a rejection.
		signOut: () =>
			logout()
				.catch(() => {})
				.finally(clearSessionToken),
	});
}
