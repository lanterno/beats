/**
 * The suspension store: the full-page notice's single source. The one
 * behavioral subtlety worth pinning is that recording a suspension ends the
 * session — but through the port's clear(), never the 401 path's redirect —
 * and that the first refusal's wording stands.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { provideSession, type SessionPort } from "@/shared/session";
import {
	recordSuspension,
	resetSuspensionForTests,
	subscribeSuspension,
	suspensionNotice,
} from "./suspension";

const signedOutDefaults: SessionPort = {
	getToken: () => null,
	getUserKey: () => null,
	subscribe: () => () => {},
	clear: () => {},
	signOut: async () => {},
};

beforeEach(resetSuspensionForTests);
afterEach(() => {
	resetSuspensionForTests();
	provideSession(signedOutDefaults);
});

describe("recordSuspension", () => {
	it("keeps the sentence, notifies, and ends the session", () => {
		const clear = vi.fn();
		provideSession({ ...signedOutDefaults, clear });
		const onChange = vi.fn();
		subscribeSuspension(onChange);

		recordSuspension("This account is suspended. Write to op@example.test.");

		expect(suspensionNotice()).toBe("This account is suspended. Write to op@example.test.");
		expect(onChange).toHaveBeenCalledTimes(1);
		expect(clear).toHaveBeenCalledTimes(1);
	});

	it("the first refusal's wording stands", () => {
		recordSuspension("first");
		recordSuspension("second");
		expect(suspensionNotice()).toBe("first");
	});
});
