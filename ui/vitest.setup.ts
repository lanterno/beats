import "@testing-library/jest-dom/vitest";

// Node 25 ships an experimental `localStorage` global that lacks `.clear()`
// and may shadow jsdom's. Replace both with a minimal in-memory Storage so
// tests see a complete Storage API and start each run with a clean slate.
function makeMemoryStorage(): Storage {
	const store = new Map<string, string>();
	return {
		get length() {
			return store.size;
		},
		clear() {
			store.clear();
		},
		getItem(key: string) {
			return store.has(key) ? (store.get(key) as string) : null;
		},
		key(index: number) {
			return Array.from(store.keys())[index] ?? null;
		},
		removeItem(key: string) {
			store.delete(key);
		},
		setItem(key: string, value: string) {
			store.set(key, String(value));
		},
	};
}

Object.defineProperty(globalThis, "localStorage", {
	value: makeMemoryStorage(),
	configurable: true,
	writable: true,
});
Object.defineProperty(globalThis, "sessionStorage", {
	value: makeMemoryStorage(),
	configurable: true,
	writable: true,
});
