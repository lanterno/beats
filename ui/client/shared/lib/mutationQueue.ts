/**
 * Generic offline mutation queue.
 *
 * Persists failed writes in IndexedDB and replays them on reconnect. Every
 * enqueued mutation carries a `clientId` UUID so the server can de-dupe under
 * retries (Stage 1.4). The queue is intentionally ordering-preserving (FIFO)
 * and drain-stops on the first persistent failure — so a write that cannot
 * ever succeed blocks later writes instead of silently dropping them.
 *
 * Upgrade note: v1 of this module stored timer-specific `{type, payload}`
 * shapes under the same `beats_offline` DB name and object store. The v2
 * schema below is strictly broader, so opening the existing DB without a
 * version bump would silently see legacy rows. We bump DB_VERSION and drop
 * any legacy store on upgrade — a clean break is fine for an offline buffer.
 */

const DB_NAME = "beats_offline";
const DB_VERSION = 2;
const STORE_NAME = "mutations";

export type HttpMethod = "POST" | "PUT" | "PATCH" | "DELETE";

export interface PendingMutation {
	id?: number;
	method: HttpMethod;
	path: string;
	body: unknown;
	clientId: string;
	enqueuedAt: string;
	attempts: number;
	lastError?: string;
}

function openDb(): Promise<IDBDatabase> {
	return new Promise((resolve, reject) => {
		const request = indexedDB.open(DB_NAME, DB_VERSION);
		request.onupgradeneeded = () => {
			const db = request.result;
			// Drop legacy v1 store if present, then create the v2 store.
			if (db.objectStoreNames.contains("events")) {
				db.deleteObjectStore("events");
			}
			if (!db.objectStoreNames.contains(STORE_NAME)) {
				db.createObjectStore(STORE_NAME, { keyPath: "id", autoIncrement: true });
			}
		};
		request.onsuccess = () => resolve(request.result);
		request.onerror = () => reject(request.error);
	});
}

export function newClientId(): string {
	if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
		return crypto.randomUUID();
	}
	// Fallback for environments without crypto.randomUUID — unreachable in Chrome 92+
	return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export async function enqueueMutation(
	mutation: Omit<PendingMutation, "id" | "enqueuedAt" | "attempts">,
): Promise<void> {
	const db = await openDb();
	return new Promise((resolve, reject) => {
		const tx = db.transaction(STORE_NAME, "readwrite");
		tx.objectStore(STORE_NAME).add({
			...mutation,
			enqueuedAt: new Date().toISOString(),
			attempts: 0,
		});
		tx.oncomplete = () => resolve();
		tx.onerror = () => reject(tx.error);
	});
}

export async function listPending(): Promise<PendingMutation[]> {
	const db = await openDb();
	return new Promise((resolve, reject) => {
		const tx = db.transaction(STORE_NAME, "readonly");
		const request = tx.objectStore(STORE_NAME).getAll();
		request.onsuccess = () => resolve(request.result as PendingMutation[]);
		request.onerror = () => reject(request.error);
	});
}

export async function removeMutation(id: number): Promise<void> {
	const db = await openDb();
	return new Promise((resolve, reject) => {
		const tx = db.transaction(STORE_NAME, "readwrite");
		tx.objectStore(STORE_NAME).delete(id);
		tx.oncomplete = () => resolve();
		tx.onerror = () => reject(tx.error);
	});
}

export async function markAttempt(id: number, error?: string): Promise<void> {
	const db = await openDb();
	return new Promise((resolve, reject) => {
		const tx = db.transaction(STORE_NAME, "readwrite");
		const store = tx.objectStore(STORE_NAME);
		const getReq = store.get(id);
		getReq.onsuccess = () => {
			const row = getReq.result as PendingMutation | undefined;
			if (!row) {
				resolve();
				return;
			}
			row.attempts += 1;
			if (error) row.lastError = error;
			store.put(row);
		};
		tx.oncomplete = () => resolve();
		tx.onerror = () => reject(tx.error);
	});
}

export async function clearAll(): Promise<void> {
	const db = await openDb();
	return new Promise((resolve, reject) => {
		const tx = db.transaction(STORE_NAME, "readwrite");
		tx.objectStore(STORE_NAME).clear();
		tx.oncomplete = () => resolve();
		tx.onerror = () => reject(tx.error);
	});
}

export interface DrainResult {
	drained: number;
	remaining: number;
	error?: string;
}

/**
 * Replay queued mutations in insertion order. Returns when either the queue
 * is empty or a replay throws — the latter keeps the mutation in place so it
 * can be retried on the next reconnect / tick.
 */
export async function drainPending(
	replay: (mutation: PendingMutation) => Promise<void>,
): Promise<DrainResult> {
	const pending = await listPending();
	let drained = 0;

	for (const mutation of pending) {
		try {
			await replay(mutation);
			if (mutation.id !== undefined) await removeMutation(mutation.id);
			drained += 1;
		} catch (err) {
			const message = err instanceof Error ? err.message : String(err);
			if (mutation.id !== undefined) await markAttempt(mutation.id, message);
			return { drained, remaining: pending.length - drained, error: message };
		}
	}

	return { drained, remaining: 0 };
}
