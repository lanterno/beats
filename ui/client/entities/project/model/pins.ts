/**
 * Pinned projects — user-scoped localStorage with a small custom-event
 * broadcast so multiple `usePinnedProjects()` consumers in different
 * components stay in sync. localStorage doesn't fire storage events for
 * same-tab writes, so we dispatch our own.
 *
 * Same key scheme as pickerRecents (P2.1) — both user-scoped by email so
 * a shared browser doesn't leak state across accounts. Server-side
 * persistence stays deferred per the roadmap (open question 2).
 */

import { useEffect, useState } from "react";
import { useAuth } from "@/features/auth";

const KEY_PREFIX = "beats:project-pins:v1";
const EVENT_NAME = "beats:pins-changed";

function keyFor(userKey: string): string {
	return `${KEY_PREFIX}:${userKey}`;
}

function canUseStorage(): boolean {
	return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

/**
 * Read the pinned set for a user. Returns an empty Set when there's no
 * user (logged-out), no storage, or the stored value is malformed.
 */
export function readPins(userKey: string | null | undefined): Set<string> {
	if (!userKey || !canUseStorage()) return new Set();
	try {
		const raw = window.localStorage.getItem(keyFor(userKey));
		if (!raw) return new Set();
		const parsed = JSON.parse(raw);
		if (!Array.isArray(parsed)) return new Set();
		return new Set(parsed.filter((x): x is string => typeof x === "string"));
	} catch {
		return new Set();
	}
}

function writePins(userKey: string, ids: Set<string>): void {
	if (!canUseStorage()) return;
	try {
		window.localStorage.setItem(keyFor(userKey), JSON.stringify([...ids]));
		// Broadcast so other usePinnedProjects() consumers re-read.
		window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: { userKey } }));
	} catch {
		// quota, private mode, etc. — preserve the picker silently
	}
}

/** Toggle pin state for a project. No-op when no user is available. */
export function togglePin(userKey: string | null | undefined, projectId: string): void {
	if (!userKey || !projectId) return;
	const pins = readPins(userKey);
	if (pins.has(projectId)) pins.delete(projectId);
	else pins.add(projectId);
	writePins(userKey, pins);
}

export function isPinned(userKey: string | null | undefined, projectId: string): boolean {
	if (!userKey || !projectId) return false;
	return readPins(userKey).has(projectId);
}

/**
 * React hook that returns the current pinned-project set for the logged-in
 * user and re-renders whenever pins change (via the custom event) or the
 * auth user flips. Same-tab listener relies on the custom event since
 * `storage` only fires across tabs.
 */
export function usePinnedProjects(): {
	pins: Set<string>;
	toggle: (projectId: string) => void;
	isPinned: (projectId: string) => boolean;
} {
	const { user } = useAuth();
	const userKey = user?.email ?? null;
	const [pins, setPins] = useState<Set<string>>(() => readPins(userKey));

	useEffect(() => {
		setPins(readPins(userKey));
		if (!userKey || typeof window === "undefined") return;
		const refresh = () => setPins(readPins(userKey));
		// FF.12: `storage` fires for EVERY localStorage write from another tab —
		// auth, timer, theme, recents, install-prompt, etc. Filter by the
		// pins key for this user (or e.key === null, which is fired by
		// localStorage.clear() and must still wipe). Otherwise unrelated
		// activity in a sibling tab re-parses pins and creates a fresh Set,
		// forcing a redundant re-render in every consumer.
		const pinsKey = keyFor(userKey);
		const onStorage = (e: StorageEvent) => {
			if (e.key === null || e.key === pinsKey) refresh();
		};
		window.addEventListener(EVENT_NAME, refresh);
		window.addEventListener("storage", onStorage);
		return () => {
			window.removeEventListener(EVENT_NAME, refresh);
			window.removeEventListener("storage", onStorage);
		};
	}, [userKey]);

	return {
		pins,
		toggle: (projectId: string) => togglePin(userKey, projectId),
		isPinned: (projectId: string) => pins.has(projectId),
	};
}

/** Test-only — wipes pins for a single user. */
export function clearPins(userKey: string | null | undefined): void {
	if (!userKey || !canUseStorage()) return;
	try {
		window.localStorage.removeItem(keyFor(userKey));
		window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: { userKey } }));
	} catch {
		// ignore
	}
}
