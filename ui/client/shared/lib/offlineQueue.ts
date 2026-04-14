/**
 * Offline Event Queue
 * Persists timer start/stop events in IndexedDB when offline.
 * Drains automatically when connectivity returns.
 */

const DB_NAME = "beats_offline";
const DB_VERSION = 1;
const STORE_NAME = "events";

interface OfflineEvent {
	id?: number;
	type: "start" | "stop";
	payload: { projectId?: string; time: string };
	createdAt: string;
}

function openDb(): Promise<IDBDatabase> {
	return new Promise((resolve, reject) => {
		const request = indexedDB.open(DB_NAME, DB_VERSION);
		request.onupgradeneeded = () => {
			const db = request.result;
			if (!db.objectStoreNames.contains(STORE_NAME)) {
				db.createObjectStore(STORE_NAME, { keyPath: "id", autoIncrement: true });
			}
		};
		request.onsuccess = () => resolve(request.result);
		request.onerror = () => reject(request.error);
	});
}

export async function enqueueEvent(event: Omit<OfflineEvent, "id" | "createdAt">): Promise<void> {
	const db = await openDb();
	return new Promise((resolve, reject) => {
		const tx = db.transaction(STORE_NAME, "readwrite");
		tx.objectStore(STORE_NAME).add({ ...event, createdAt: new Date().toISOString() });
		tx.oncomplete = () => resolve();
		tx.onerror = () => reject(tx.error);
	});
}

export async function getPendingEvents(): Promise<OfflineEvent[]> {
	const db = await openDb();
	return new Promise((resolve, reject) => {
		const tx = db.transaction(STORE_NAME, "readonly");
		const request = tx.objectStore(STORE_NAME).getAll();
		request.onsuccess = () => resolve(request.result);
		request.onerror = () => reject(request.error);
	});
}

async function clearEvents(): Promise<void> {
	const db = await openDb();
	return new Promise((resolve, reject) => {
		const tx = db.transaction(STORE_NAME, "readwrite");
		tx.objectStore(STORE_NAME).clear();
		tx.oncomplete = () => resolve();
		tx.onerror = () => reject(tx.error);
	});
}

/**
 * Replay all queued events in order, then clear the store.
 * Returns the number of events successfully replayed.
 */
export async function drainQueue(replay: (event: OfflineEvent) => Promise<void>): Promise<number> {
	const events = await getPendingEvents();
	if (events.length === 0) return 0;

	let replayed = 0;
	for (const event of events) {
		try {
			await replay(event);
			replayed++;
		} catch {
			// If replay fails (still offline), stop draining
			break;
		}
	}

	if (replayed === events.length) {
		await clearEvents();
	}
	return replayed;
}
