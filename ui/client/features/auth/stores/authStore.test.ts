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

// Only the API saying the session is over (a 401) ends it. A network error or
// a 5xx is the API being down, and signing everyone out of an outage would
// leave them a passkey ceremony away from their timer once it is back.
describe("authStore through an API outage", () => {
	let store: typeof import("./authStore");
	const token = fakeJwt(Math.floor(Date.now() / 1000) + 3600);
	const me = { email: "a@example.com", display_name: null, identities: [], sso_provisioned: false };
	const json = (status: number, body: unknown) =>
		new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

	beforeEach(async () => {
		localStorage.clear();
		vi.resetModules();
		// A 401 sends the browser home; jsdom cannot navigate.
		Object.defineProperty(window, "location", {
			configurable: true,
			value: { ...window.location, replace: vi.fn() },
		});
		store = await import("./authStore");
		// Wired as app/session.ts wires it, so the API client's 401 reaches the store.
		const { provideSession } = await import("@/shared/session");
		provideSession({
			getToken: store.getSessionToken,
			getUserKey: store.getAuthUserKey,
			subscribe: store.subscribeToAuth,
			clear: store.clearSessionToken,
			signOut: async () => {},
		});
	});

	afterEach(() => {
		store.clearSessionToken();
		vi.unstubAllGlobals();
		vi.useRealTimers();
		localStorage.clear();
	});

	it("ends the session when /me answers 401", async () => {
		localStorage.setItem("beats_session_token", token);
		vi.stubGlobal(
			"fetch",
			vi.fn(async () => json(401, { detail: "Token expired", code: "UNAUTHORIZED" })),
		);
		await store.initializeAuth();
		expect(store.isAuthenticated()).toBe(false);
		expect(localStorage.getItem("beats_session_token")).toBeNull();
	});

	it.each([
		["the network fails", () => Promise.reject(new TypeError("Failed to fetch"))],
		["the API answers 503", async () => json(503, { detail: "Unavailable" })],
	])("keeps the session when %s, and asks /me again", async (_, failure) => {
		vi.useFakeTimers();
		localStorage.setItem("beats_session_token", token);
		const fetchMock = vi.fn(failure);
		vi.stubGlobal("fetch", fetchMock);

		await store.initializeAuth();
		expect(store.isAuthenticated()).toBe(true);
		expect(store.getSessionToken()).toBe(token);
		expect(localStorage.getItem("beats_session_token")).toBe(token);

		fetchMock.mockImplementation(async () => json(200, me));
		await vi.advanceTimersByTimeAsync(30_000);
		await vi.waitFor(() => expect(store.getAuthUserKey()).toBe("a@example.com"));
	});

	it("keeps the session when a refresh meets a failing API, and ends it when the refresh is refused", async () => {
		vi.useFakeTimers();
		// Four minutes left: inside the five the refresh is scheduled ahead by.
		const expiring = fakeJwt(Math.floor(Date.now() / 1000) + 240);
		localStorage.setItem("beats_session_token", expiring);
		let refresh = 503;
		vi.stubGlobal(
			"fetch",
			vi.fn(async (url: string) =>
				String(url).endsWith("/api/account/refresh")
					? json(refresh, { detail: "No", code: refresh === 401 ? "UNAUTHORIZED" : "UNAVAILABLE" })
					: json(200, me),
			),
		);

		await store.initializeAuth();
		await vi.advanceTimersByTimeAsync(0);
		expect(store.isAuthenticated()).toBe(true);
		expect(store.getSessionToken()).toBe(expiring);

		refresh = 401;
		await vi.advanceTimersByTimeAsync(30_000);
		await vi.waitFor(() => expect(store.isAuthenticated()).toBe(false));
	});
});
