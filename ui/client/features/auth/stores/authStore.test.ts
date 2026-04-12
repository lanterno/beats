import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Build a fake JWT with a given exp timestamp (seconds since epoch).
function fakeJwt(exp: number): string {
	const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
	const payload = btoa(JSON.stringify({ sub: "user-1", exp, type: "session" }));
	return `${header}.${payload}.fake-signature`;
}

describe("authStore token expiry", () => {
	let store: typeof import("./authStore");

	beforeEach(async () => {
		localStorage.clear();
		// Re-import to reset module-level state
		vi.resetModules();
		store = await import("./authStore");
	});

	afterEach(() => {
		localStorage.clear();
	});

	it("getSessionToken returns null when token is expired", () => {
		const expiredExp = Math.floor(Date.now() / 1000) - 120; // 2 min ago
		const token = fakeJwt(expiredExp);
		store.setSessionToken(token);

		expect(store.getSessionToken()).toBeNull();
		expect(store.isAuthenticated()).toBe(false);
	});

	it("getSessionToken returns null when token expires within buffer window", () => {
		const almostExpiredExp = Math.floor(Date.now() / 1000) + 30; // 30s from now (< 60s buffer)
		const token = fakeJwt(almostExpiredExp);
		store.setSessionToken(token);

		expect(store.getSessionToken()).toBeNull();
	});

	it("getSessionToken returns token when it is still valid", () => {
		const validExp = Math.floor(Date.now() / 1000) + 3600; // 1h from now
		const token = fakeJwt(validExp);
		store.setSessionToken(token);

		expect(store.getSessionToken()).toBe(token);
	});

	it("getSessionToken returns null for malformed token", () => {
		store.setSessionToken("not-a-jwt");

		expect(store.getSessionToken()).toBeNull();
	});

	it("clearSessionToken clears auth state", () => {
		const validExp = Math.floor(Date.now() / 1000) + 3600;
		store.setSessionToken(fakeJwt(validExp));
		expect(store.isAuthenticated()).toBe(true);

		store.clearSessionToken();
		expect(store.getSessionToken()).toBeNull();
		expect(store.isAuthenticated()).toBe(false);
	});
});
