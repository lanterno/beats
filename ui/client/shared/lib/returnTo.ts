/**
 * Where to go once signed in. A page behind `ProtectedRoute` opened while
 * signed out — an organisation's invite URL in a mail, a project link on a
 * new machine — sends the visitor to the homepage to sign in; without this,
 * the path they came for was lost on the way. The path is kept for this
 * tab alone (sessionStorage) and taken once.
 *
 * Only a path on this origin is ever returned: a stored value that does not
 * start with a single `/` — an absolute URL, a protocol-relative one — is
 * dropped, so nothing here can send a sign-in to another site.
 */

const KEY = "beats_return_to";

type Storage = Pick<globalThis.Storage, "getItem" | "setItem" | "removeItem">;

function store(): Storage | null {
	try {
		return window.sessionStorage;
	} catch {
		return null;
	}
}

/** Keep `path` (with its search) for after sign-in. The homepage itself is not worth keeping. */
export function rememberReturnTo(path: string, storage: Storage | null = store()): void {
	if (!storage || !isLocalPath(path) || path === "/" || path === "/app") return;
	storage.setItem(KEY, path);
}

/** The path kept, if any, cleared on the way out. */
export function takeReturnTo(storage: Storage | null = store()): string | null {
	if (!storage) return null;
	const path = storage.getItem(KEY);
	storage.removeItem(KEY);
	return path !== null && isLocalPath(path) ? path : null;
}

function isLocalPath(path: string): boolean {
	return path.startsWith("/") && !path.startsWith("//") && !path.includes("\\");
}
