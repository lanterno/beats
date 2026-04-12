import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useOnlineStatus } from "./useOnlineStatus";

describe("useOnlineStatus", () => {
	it("returns true when browser is online", () => {
		const { result } = renderHook(() => useOnlineStatus());
		// jsdom defaults navigator.onLine to true
		expect(result.current).toBe(true);
	});

	it("updates to false on offline event", () => {
		const { result } = renderHook(() => useOnlineStatus());

		act(() => {
			window.dispatchEvent(new Event("offline"));
		});

		expect(result.current).toBe(false);
	});

	it("updates to true on online event", () => {
		const { result } = renderHook(() => useOnlineStatus());

		act(() => {
			window.dispatchEvent(new Event("offline"));
		});
		expect(result.current).toBe(false);

		act(() => {
			window.dispatchEvent(new Event("online"));
		});
		expect(result.current).toBe(true);
	});

	it("cleans up event listeners on unmount", () => {
		const addSpy = vi.spyOn(window, "addEventListener");
		const removeSpy = vi.spyOn(window, "removeEventListener");

		const { unmount } = renderHook(() => useOnlineStatus());

		expect(addSpy).toHaveBeenCalledWith("online", expect.any(Function));
		expect(addSpy).toHaveBeenCalledWith("offline", expect.any(Function));

		unmount();

		expect(removeSpy).toHaveBeenCalledWith("online", expect.any(Function));
		expect(removeSpy).toHaveBeenCalledWith("offline", expect.any(Function));

		addSpy.mockRestore();
		removeSpy.mockRestore();
	});
});
