/**
 * Sync engine — drains the offline mutation queue on reconnect and on a slow
 * interval (belt + braces for tabs that miss the `online` event). Exposes the
 * pending count and a syncing flag for header status UI.
 *
 * The engine is a singleton by design: instantiate it once at the app root
 * (Layout) via `useSyncEngine()`, then read its observable state anywhere via
 * `useSyncStatus()`. Multiple drains cannot overlap — the engine holds a local
 * mutex.
 */

import { useEffect, useState } from "react";
import { ApiError, replayMutation } from "@/shared/api";
import { drainPending, listPending, type PendingMutation } from "./mutationQueue";

const IDLE_POLL_MS = 30_000;
const ACTIVE_POLL_MS = 5_000;

type Listener = (snapshot: SyncSnapshot) => void;

export interface SyncSnapshot {
	pendingCount: number;
	syncing: boolean;
	online: boolean;
	lastError?: string;
}

class SyncController {
	private listeners = new Set<Listener>();
	private snapshot: SyncSnapshot = {
		pendingCount: 0,
		syncing: false,
		online: typeof navigator === "undefined" ? true : navigator.onLine,
	};
	private draining = false;
	private started = false;
	private stopFns: Array<() => void> = [];

	subscribe(listener: Listener): () => void {
		this.listeners.add(listener);
		listener(this.snapshot);
		return () => {
			this.listeners.delete(listener);
		};
	}

	getSnapshot(): SyncSnapshot {
		return this.snapshot;
	}

	private emit(partial: Partial<SyncSnapshot>) {
		this.snapshot = { ...this.snapshot, ...partial };
		for (const l of this.listeners) l(this.snapshot);
	}

	async refreshPending(): Promise<void> {
		try {
			const pending = await listPending();
			this.emit({ pendingCount: pending.length });
		} catch {
			// IndexedDB unavailable (private mode, SSR, tests) — leave count as-is.
		}
	}

	async drain(): Promise<void> {
		if (this.draining) return;
		this.draining = true;
		this.emit({ syncing: true });
		try {
			const result = await drainPending(replayPoisonAware);
			await this.refreshPending();
			this.emit({ syncing: false, lastError: result.error });
		} finally {
			this.draining = false;
		}
	}

	start(): void {
		if (this.started) return;
		this.started = true;

		const onOnline = () => {
			this.emit({ online: true });
			void this.drain();
		};
		const onOffline = () => this.emit({ online: false });

		if (typeof window !== "undefined") {
			window.addEventListener("online", onOnline);
			window.addEventListener("offline", onOffline);
			this.stopFns.push(() => window.removeEventListener("online", onOnline));
			this.stopFns.push(() => window.removeEventListener("offline", onOffline));
		}

		// Poll: fast when there is work to do, slow when idle.
		let timer: ReturnType<typeof setTimeout> | undefined;
		const schedule = () => {
			const delay = this.snapshot.pendingCount > 0 ? ACTIVE_POLL_MS : IDLE_POLL_MS;
			timer = setTimeout(async () => {
				if (this.snapshot.online && this.snapshot.pendingCount > 0) {
					await this.drain();
				} else {
					await this.refreshPending();
				}
				schedule();
			}, delay);
		};
		schedule();
		this.stopFns.push(() => {
			if (timer) clearTimeout(timer);
		});

		void this.refreshPending().then(() => {
			if (this.snapshot.online && this.snapshot.pendingCount > 0) void this.drain();
		});
	}

	stop(): void {
		for (const fn of this.stopFns) fn();
		this.stopFns = [];
		this.started = false;
	}
}

const controller = new SyncController();

/**
 * Replay a queued mutation with "poison-aware" handling: if the
 * server returns a 4xx, the mutation is permanently dropped from
 * the queue (resolves successfully so drainPending removes it).
 * Network errors and 5xx still bubble up so the queue keeps the
 * mutation for the next reconnect.
 *
 * Without this, a single poisoned mutation (validation against a
 * since-changed schema, a 404 for a deleted project, an
 * unprocessable body from an old client version) would block
 * every subsequent drain forever — drainPending stops on the
 * first error, attempts increment indefinitely, and mutations
 * after the bad one never get tried.
 *
 * Exported for testing.
 */
export async function replayPoisonAware(mutation: PendingMutation): Promise<void> {
	try {
		await replayMutation(mutation);
	} catch (err) {
		if (err instanceof ApiError && err.statusCode >= 400 && err.statusCode < 500) {
			// Server-confirmed permanent failure — log and drop. The
			// alternative (keep retrying) would never succeed and
			// would block the rest of the queue.
			// biome-ignore lint/suspicious/noConsole: surfacing to dev console is the point
			console.warn(
				`[sync] dropping poisoned mutation ${mutation.method} ${mutation.path}: ${err.message}`,
			);
			return;
		}
		throw err;
	}
}

/** Notify the engine that new work was enqueued — triggers an opportunistic drain. */
export function notifySyncWork(): void {
	void controller.refreshPending().then(() => {
		if (controller.getSnapshot().online) void controller.drain();
	});
}

/**
 * Install the engine at the app root. Call this **exactly once**, inside
 * `Layout.tsx`. It starts the singleton controller (online/offline listeners,
 * poll loop, initial drain) and returns a live snapshot.
 *
 * Any other component that just needs to display sync state must call
 * {@link useSyncStatus} instead — invoking `useSyncEngine` multiple times is
 * a no-op (the controller's `start()` is idempotent) but carries the wrong
 * intent and will confuse future readers.
 */
export function useSyncEngine(): SyncSnapshot {
	const [snapshot, setSnapshot] = useState<SyncSnapshot>(() => controller.getSnapshot());

	useEffect(() => {
		controller.start();
		const unsubscribe = controller.subscribe(setSnapshot);
		return () => {
			unsubscribe();
		};
	}, []);

	return snapshot;
}

/**
 * Subscribe to sync state. Safe to call from any component; does NOT start
 * the engine — that happens once in `Layout.tsx` via {@link useSyncEngine}.
 * Use this hook for header badges, settings panels, or any read-only UI.
 */
export function useSyncStatus(): SyncSnapshot {
	const [snapshot, setSnapshot] = useState<SyncSnapshot>(() => controller.getSnapshot());
	useEffect(() => controller.subscribe(setSnapshot), []);
	return snapshot;
}
