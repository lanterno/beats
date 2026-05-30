/**
 * Picker recents — most-recently-selected project ids, user-scoped to avoid
 * cross-account leakage on the same browser. Read by the ProjectPicker
 * (boosts recents to the top with an empty query) and written on every
 * selection. localStorage is the storage today; P2.5 (pin-to-top) reuses
 * the same key scheme; server-side persistence stays deferred per the
 * roadmap.
 */

const KEY_PREFIX = "beats:project-picker-recents:v1";
const MAX_RECENTS = 8;

function keyFor(userKey: string): string {
	return `${KEY_PREFIX}:${userKey}`;
}

function canUseStorage(): boolean {
	return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

/**
 * Read the recents list for the given user. Returns [] when there's no user
 * (logged-out), no storage, or the stored value is malformed — the picker
 * silently degrades to its no-query "all projects in order" rendering.
 */
export function readPickerRecents(userKey: string | null | undefined): string[] {
	if (!userKey || !canUseStorage()) return [];
	try {
		const raw = window.localStorage.getItem(keyFor(userKey));
		if (!raw) return [];
		const parsed = JSON.parse(raw);
		if (!Array.isArray(parsed)) return [];
		return parsed.filter((x): x is string => typeof x === "string");
	} catch {
		return [];
	}
}

/**
 * Record `projectId` as the most-recent selection for `userKey`. Dedupes (the
 * id moves to the front rather than appearing twice) and caps the list at
 * MAX_RECENTS. Silently no-ops if storage is unavailable.
 */
export function recordPickerRecent(userKey: string | null | undefined, projectId: string): void {
	if (!userKey || !projectId || !canUseStorage()) return;
	const existing = readPickerRecents(userKey);
	const next = [projectId, ...existing.filter((id) => id !== projectId)].slice(0, MAX_RECENTS);
	try {
		window.localStorage.setItem(keyFor(userKey), JSON.stringify(next));
	} catch {
		// Quota exceeded, private mode, etc. — preserving the picker is more
		// important than cluttering the user with errors.
	}
}

/** Test-only — wipes the stored recents for a single user. */
export function clearPickerRecents(userKey: string | null | undefined): void {
	if (!userKey || !canUseStorage()) return;
	try {
		window.localStorage.removeItem(keyFor(userKey));
	} catch {
		// ignore
	}
}
