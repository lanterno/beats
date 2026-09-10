import { beforeEach, describe, expect, it, vi } from "vitest";
import { endSession, provideSession, sessionToken, signOut } from "./index";

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
