import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useUrlParam } from "./useUrlParam";

afterEach(() => {
	window.history.replaceState({}, "", "/");
});

describe("useUrlParam", () => {
	it("reads the initial value from the current URL", () => {
		window.history.replaceState({}, "", "/insights?repo=%2FUsers%2Fme%2Fbeats");
		const { result } = renderHook(() => useUrlParam("repo"));
		expect(result.current[0]).toBe("/Users/me/beats");
	});

	it("returns undefined when the param is absent", () => {
		window.history.replaceState({}, "", "/insights");
		const { result } = renderHook(() => useUrlParam("repo"));
		expect(result.current[0]).toBeUndefined();
	});

	it("writes the value into the URL on update", () => {
		window.history.replaceState({}, "", "/insights");
		const { result } = renderHook(() => useUrlParam("language"));

		act(() => result.current[1]("go"));

		expect(result.current[0]).toBe("go");
		expect(window.location.search).toBe("?language=go");
	});

	it("removes the param when set to undefined", () => {
		window.history.replaceState({}, "", "/insights?language=go&repo=foo");
		const { result } = renderHook(() => useUrlParam("language"));

		act(() => result.current[1](undefined));

		expect(window.location.search).toBe("?repo=foo");
	});

	it("removes the param when set to empty string", () => {
		window.history.replaceState({}, "", "/insights?bundle=com.x");
		const { result } = renderHook(() => useUrlParam("bundle"));

		act(() => result.current[1](""));

		expect(window.location.search).toBe("");
	});

	it("preserves other params when updating one key", () => {
		window.history.replaceState({}, "", "/insights?language=go");
		const { result } = renderHook(() => useUrlParam("repo"));

		act(() => result.current[1]("/Users/me/beats"));

		// Order isn't guaranteed by URLSearchParams across runtimes; verify
		// both pairs survived rather than the literal string.
		const params = new URLSearchParams(window.location.search);
		expect(params.get("language")).toBe("go");
		expect(params.get("repo")).toBe("/Users/me/beats");
	});

	it("uses replaceState — no extra history entry per click", () => {
		window.history.replaceState({}, "", "/insights");
		const beforeLength = window.history.length;

		const { result } = renderHook(() => useUrlParam("repo"));
		act(() => result.current[1]("/Users/me/beats"));
		act(() => result.current[1]("/Users/me/other"));
		act(() => result.current[1](undefined));

		expect(window.history.length).toBe(beforeLength);
	});

	it("syncs with popstate so back/forward updates the value", () => {
		window.history.replaceState({}, "", "/insights?repo=first");
		const { result } = renderHook(() => useUrlParam("repo"));
		expect(result.current[0]).toBe("first");

		act(() => {
			window.history.replaceState({}, "", "/insights?repo=second");
			window.dispatchEvent(new PopStateEvent("popstate"));
		});

		expect(result.current[0]).toBe("second");
	});
});
