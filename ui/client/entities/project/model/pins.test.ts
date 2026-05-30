import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clearPins, isPinned, readPins, togglePin, usePinnedProjects } from "./pins";

vi.mock("@/features/auth", () => ({
	useAuth: () => ({ user: { email: "alice@example.com" } }),
}));

const USER = "alice@example.com";

describe("pins module", () => {
	beforeEach(() => {
		window.localStorage.clear();
	});

	it("readPins returns an empty Set when there is no user", () => {
		expect(readPins(null).size).toBe(0);
		expect(readPins(undefined).size).toBe(0);
	});

	it("togglePin flips state and persists per-user", () => {
		togglePin(USER, "p1");
		togglePin(USER, "p2");
		expect([...readPins(USER)].sort()).toEqual(["p1", "p2"]);
		togglePin(USER, "p1");
		expect([...readPins(USER)]).toEqual(["p2"]);
	});

	it("isPinned reflects the current state", () => {
		togglePin(USER, "p1");
		expect(isPinned(USER, "p1")).toBe(true);
		expect(isPinned(USER, "p2")).toBe(false);
		expect(isPinned(null, "p1")).toBe(false);
	});

	it("scopes by user", () => {
		togglePin(USER, "p1");
		togglePin("bob@example.com", "p2");
		expect([...readPins(USER)]).toEqual(["p1"]);
		expect([...readPins("bob@example.com")]).toEqual(["p2"]);
	});

	it("recovers from corrupt storage", () => {
		window.localStorage.setItem("beats:project-pins:v1:alice@example.com", "garbage{");
		expect(readPins(USER).size).toBe(0);
	});

	it("clearPins wipes only the targeted user", () => {
		togglePin(USER, "p1");
		togglePin("bob@example.com", "p2");
		clearPins(USER);
		expect(readPins(USER).size).toBe(0);
		expect([...readPins("bob@example.com")]).toEqual(["p2"]);
	});
});

describe("usePinnedProjects", () => {
	beforeEach(() => {
		window.localStorage.clear();
	});

	it("re-renders when togglePin fires the custom event", () => {
		const { result } = renderHook(() => usePinnedProjects());
		expect(result.current.pins.size).toBe(0);

		act(() => {
			result.current.toggle("p1");
		});
		// Same-tab listener catches our custom event (the storage event
		// only fires across tabs, so without the broadcast this would stay
		// at size 0).
		expect(result.current.isPinned("p1")).toBe(true);
		expect([...result.current.pins]).toEqual(["p1"]);
	});
});
