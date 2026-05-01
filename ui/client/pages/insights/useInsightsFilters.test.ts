/**
 * Tests for useInsightsFilters. The hook owns three things worth
 * locking in:
 *
 * - URL persistence (delegated to useUrlParam, but cover the wiring
 *   so a refactor that swaps the param key would surface here).
 * - activeFilterCount math — the "× clear all filters" header link
 *   in Insights uses this for its 2+ visibility threshold; an off-
 *   by-one regression would silently hide the affordance.
 * - clearAllFilters wipes every axis. This is the contract that
 *   currently has no end-to-end test, and the kind of thing that's
 *   easy to forget to extend when a new filter axis is added.
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { shouldHandleEscClear, useInsightsFilters } from "./useInsightsFilters";

afterEach(() => {
	window.history.replaceState({}, "", "/");
});

describe("useInsightsFilters", () => {
	it("hydrates each axis from the URL on mount", () => {
		window.history.replaceState(
			{},
			"",
			"/insights?project=p1&tag=ops&repo=%2FUsers%2Fme%2Fcode%2Fbeats&language=go&bundle=com.microsoft.VSCode",
		);
		const { result } = renderHook(() => useInsightsFilters());

		expect(result.current.selectedProjectId).toBe("p1");
		expect(result.current.selectedTag).toBe("ops");
		expect(result.current.selectedRepo).toBe("/Users/me/code/beats");
		expect(result.current.selectedLanguage).toBe("go");
		expect(result.current.selectedBundleId).toBe("com.microsoft.VSCode");
	});

	it("activeFilterCount is 0 when the URL is bare", () => {
		window.history.replaceState({}, "", "/insights");
		const { result } = renderHook(() => useInsightsFilters());
		expect(result.current.activeFilterCount).toBe(0);
	});

	it("activeFilterCount counts each non-empty axis", () => {
		window.history.replaceState({}, "", "/insights?project=p1&language=go");
		const { result } = renderHook(() => useInsightsFilters());
		expect(result.current.activeFilterCount).toBe(2);
	});

	it("activeFilterCount reaches all 5 when every axis is set", () => {
		window.history.replaceState({}, "", "/insights?project=p&tag=t&repo=r&language=l&bundle=b");
		const { result } = renderHook(() => useInsightsFilters());
		expect(result.current.activeFilterCount).toBe(5);
	});

	it("setting an axis writes to the URL and updates the count", () => {
		window.history.replaceState({}, "", "/insights");
		const { result } = renderHook(() => useInsightsFilters());

		expect(result.current.activeFilterCount).toBe(0);
		act(() => result.current.setSelectedRepo("/Users/me/code/beats"));

		expect(result.current.selectedRepo).toBe("/Users/me/code/beats");
		expect(result.current.activeFilterCount).toBe(1);
		expect(new URLSearchParams(window.location.search).get("repo")).toBe("/Users/me/code/beats");
	});

	it("clearAllFilters wipes every axis in one shot", () => {
		// Same regression class that's easiest to forget when adding a
		// new axis: clearAllFilters omits one of the setters and that
		// axis silently survives the reset.
		window.history.replaceState({}, "", "/insights?project=p&tag=t&repo=r&language=l&bundle=b");
		const { result } = renderHook(() => useInsightsFilters());
		expect(result.current.activeFilterCount).toBe(5);

		act(() => result.current.clearAllFilters());

		expect(result.current.activeFilterCount).toBe(0);
		expect(result.current.selectedProjectId).toBeUndefined();
		expect(result.current.selectedTag).toBeUndefined();
		expect(result.current.selectedRepo).toBeUndefined();
		expect(result.current.selectedLanguage).toBeUndefined();
		expect(result.current.selectedBundleId).toBeUndefined();

		// And the URL shouldn't carry any of the keys anymore.
		const params = new URLSearchParams(window.location.search);
		for (const key of ["project", "tag", "repo", "language", "bundle"]) {
			expect(params.has(key)).toBe(false);
		}
	});
});

describe("shouldHandleEscClear", () => {
	function fakeEvent(overrides: Partial<KeyboardEvent> = {}): KeyboardEvent {
		// Build a minimal KeyboardEvent-shaped object — vitest's jsdom
		// supports new KeyboardEvent() but we want to control target
		// directly which is simpler with a plain object cast.
		return {
			key: "Escape",
			metaKey: false,
			ctrlKey: false,
			altKey: false,
			shiftKey: false,
			target: document.body,
			...overrides,
		} as unknown as KeyboardEvent;
	}

	it("fires when Escape pressed with active filters and no modifiers", () => {
		expect(shouldHandleEscClear(fakeEvent(), true)).toBe(true);
	});

	it("does not fire when no filters are active", () => {
		// Esc on a clean page should be a no-op — we don't want to
		// preventDefault unnecessarily and shadow whatever else might
		// listen to Esc on the page.
		expect(shouldHandleEscClear(fakeEvent(), false)).toBe(false);
	});

	it("does not fire on keys other than Escape", () => {
		expect(shouldHandleEscClear(fakeEvent({ key: "k" }), true)).toBe(false);
		expect(shouldHandleEscClear(fakeEvent({ key: " " }), true)).toBe(false);
	});

	it("does not fire when any modifier is held", () => {
		// Cmd+Esc / Ctrl+Esc / etc. are typically reserved for
		// browser or OS shortcuts; we shouldn't shadow them.
		expect(shouldHandleEscClear(fakeEvent({ metaKey: true }), true)).toBe(false);
		expect(shouldHandleEscClear(fakeEvent({ ctrlKey: true }), true)).toBe(false);
		expect(shouldHandleEscClear(fakeEvent({ altKey: true }), true)).toBe(false);
		expect(shouldHandleEscClear(fakeEvent({ shiftKey: true }), true)).toBe(false);
	});

	it("does not fire when an input is focused", () => {
		// Esc on a search input should let the input handle it
		// (cancel/dismiss) — locking that in so a refactor can't
		// silently steal Esc from form controls.
		const input = document.createElement("input");
		expect(shouldHandleEscClear(fakeEvent({ target: input }), true)).toBe(false);

		const textarea = document.createElement("textarea");
		expect(shouldHandleEscClear(fakeEvent({ target: textarea }), true)).toBe(false);

		const select = document.createElement("select");
		expect(shouldHandleEscClear(fakeEvent({ target: select }), true)).toBe(false);
	});

	it("does not fire when a contenteditable element is focused", () => {
		const div = document.createElement("div");
		Object.defineProperty(div, "isContentEditable", { value: true });
		expect(shouldHandleEscClear(fakeEvent({ target: div }), true)).toBe(false);
	});

	it("fires when target is null (defensive)", () => {
		// Some keyboard events arrive without a target (e.g. the
		// document gained focus from a chrome shortcut). Don't refuse
		// to clear in that case — the user clearly intends Esc to do
		// SOMETHING.
		expect(shouldHandleEscClear(fakeEvent({ target: null }), true)).toBe(true);
	});
});
