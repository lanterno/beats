import { beforeEach, describe, expect, it, vi } from "vitest";
import { endSession, provideSession, sessionAccountId, sessionToken, signOut } from "./index";

const signedOutDefaults = {
	getToken: () => null,
	getUserKey: () => null,
	subscribe: () => () => {},
	clear: () => {},
	signOut: async () => {},
};

describe("session port", () => {
	beforeEach(() => {
		provideSession(signedOutDefaults);
	});

	it("reads through to whatever the app wired in", () => {
		provideSession({ ...signedOutDefaults, getToken: () => "jwt" });
		expect(sessionToken()).toBe("jwt");
	});

	it("reports a signed-out visitor before anything is wired", () => {
		expect(sessionToken()).toBeNull();
	});

	it("clearing and signing out before wiring are no-ops, not crashes", async () => {
		expect(() => endSession()).not.toThrow();
		await expect(signOut()).resolves.toBeUndefined();
	});

	it("forwards the local clear without touching the server", () => {
		const clear = vi.fn();
		const remote = vi.fn();
		provideSession({ ...signedOutDefaults, clear, signOut: remote });

		endSession();

		expect(clear).toHaveBeenCalledOnce();
		expect(remote).not.toHaveBeenCalled();
	});

	it("a later provideSession replaces the previous wiring", () => {
		provideSession({ ...signedOutDefaults, getToken: () => "first" });
		provideSession({ ...signedOutDefaults, getToken: () => "second" });
		expect(sessionToken()).toBe("second");
	});
});

describe("sessionAccountId", () => {
	it("reads the token's sub synchronously", () => {
		const payload = btoa(JSON.stringify({ sub: "u-42", exp: 9999999999 }));
		provideSession({ ...signedOutDefaults, getToken: () => `h.${payload}.s` });
		expect(sessionAccountId()).toBe("u-42");
	});

	it("null when signed out or the token is unreadable", () => {
		provideSession(signedOutDefaults);
		expect(sessionAccountId()).toBeNull();
		provideSession({ ...signedOutDefaults, getToken: () => "not-a-jwt" });
		expect(sessionAccountId()).toBeNull();
	});
});
