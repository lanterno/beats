import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useKeyboardShortcuts } from "./useKeyboardShortcuts";

function fireKey(key: string, opts: Partial<KeyboardEventInit> = {}) {
	window.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, ...opts }));
}

describe("useKeyboardShortcuts", () => {
	it("triggers toggleTimer on Space", () => {
		const actions = {
			toggleTimer: vi.fn(),
			selectProject: vi.fn(),
			openCommandPalette: vi.fn(),
			toggleFocusMode: vi.fn(),
		};

		renderHook(() => useKeyboardShortcuts(actions));
		fireKey(" ", { code: "Space" });

		expect(actions.toggleTimer).toHaveBeenCalledOnce();
	});

	it("triggers openCommandPalette on Cmd+K", () => {
		const actions = {
			toggleTimer: vi.fn(),
			selectProject: vi.fn(),
			openCommandPalette: vi.fn(),
			toggleFocusMode: vi.fn(),
		};

		renderHook(() => useKeyboardShortcuts(actions));
		fireKey("k", { metaKey: true });

		expect(actions.openCommandPalette).toHaveBeenCalledOnce();
	});

	it("triggers openCommandPalette on Ctrl+K", () => {
		const actions = {
			toggleTimer: vi.fn(),
			selectProject: vi.fn(),
			openCommandPalette: vi.fn(),
			toggleFocusMode: vi.fn(),
		};

		renderHook(() => useKeyboardShortcuts(actions));
		fireKey("k", { ctrlKey: true });

		expect(actions.openCommandPalette).toHaveBeenCalledOnce();
	});

	it("triggers openCommandPalette on /", () => {
		const actions = {
			toggleTimer: vi.fn(),
			selectProject: vi.fn(),
			openCommandPalette: vi.fn(),
			toggleFocusMode: vi.fn(),
		};

		renderHook(() => useKeyboardShortcuts(actions));
		fireKey("/");

		expect(actions.openCommandPalette).toHaveBeenCalledOnce();
	});

	it("triggers toggleFocusMode on F", () => {
		const actions = {
			toggleTimer: vi.fn(),
			selectProject: vi.fn(),
			openCommandPalette: vi.fn(),
			toggleFocusMode: vi.fn(),
		};

		renderHook(() => useKeyboardShortcuts(actions));
		fireKey("f");

		expect(actions.toggleFocusMode).toHaveBeenCalledOnce();
	});

	it("triggers selectProject with correct index for number keys", () => {
		const actions = {
			toggleTimer: vi.fn(),
			selectProject: vi.fn(),
			openCommandPalette: vi.fn(),
			toggleFocusMode: vi.fn(),
		};

		renderHook(() => useKeyboardShortcuts(actions));
		fireKey("1");
		fireKey("3");
		fireKey("9");

		expect(actions.selectProject).toHaveBeenCalledTimes(3);
		expect(actions.selectProject).toHaveBeenNthCalledWith(1, 0);
		expect(actions.selectProject).toHaveBeenNthCalledWith(2, 2);
		expect(actions.selectProject).toHaveBeenNthCalledWith(3, 8);
	});

	it("does not trigger shortcuts when input is focused", () => {
		const actions = {
			toggleTimer: vi.fn(),
			selectProject: vi.fn(),
			openCommandPalette: vi.fn(),
			toggleFocusMode: vi.fn(),
		};

		renderHook(() => useKeyboardShortcuts(actions));

		// Create and focus an input element
		const input = document.createElement("input");
		document.body.appendChild(input);
		input.focus();

		fireKey(" ", { code: "Space" });
		fireKey("f");
		fireKey("/");
		fireKey("1");

		// None of the non-meta shortcuts should fire
		expect(actions.toggleTimer).not.toHaveBeenCalled();
		expect(actions.toggleFocusMode).not.toHaveBeenCalled();
		expect(actions.selectProject).not.toHaveBeenCalled();

		document.body.removeChild(input);
	});

	it("still triggers Cmd+K when input is focused", () => {
		const actions = {
			toggleTimer: vi.fn(),
			selectProject: vi.fn(),
			openCommandPalette: vi.fn(),
			toggleFocusMode: vi.fn(),
		};

		renderHook(() => useKeyboardShortcuts(actions));

		const input = document.createElement("input");
		document.body.appendChild(input);
		input.focus();

		fireKey("k", { metaKey: true });

		expect(actions.openCommandPalette).toHaveBeenCalledOnce();

		document.body.removeChild(input);
	});

	it("cleans up listeners on unmount", () => {
		const actions = {
			toggleTimer: vi.fn(),
			selectProject: vi.fn(),
			openCommandPalette: vi.fn(),
			toggleFocusMode: vi.fn(),
		};

		const { unmount } = renderHook(() => useKeyboardShortcuts(actions));
		unmount();

		fireKey(" ", { code: "Space" });
		expect(actions.toggleTimer).not.toHaveBeenCalled();
	});
});
