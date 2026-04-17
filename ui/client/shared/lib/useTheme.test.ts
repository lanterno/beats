import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useTheme } from "./useTheme";

// Node 25 built-in localStorage has limited API — mock it for reliable tests
const store: Record<string, string> = {};
const mockStorage = {
	getItem: vi.fn((key: string) => store[key] ?? null),
	setItem: vi.fn((key: string, value: string) => {
		store[key] = value;
	}),
	removeItem: vi.fn((key: string) => {
		delete store[key];
	}),
	clear: vi.fn(() => {
		for (const key of Object.keys(store)) delete store[key];
	}),
	get length() {
		return Object.keys(store).length;
	},
	key: vi.fn((i: number) => Object.keys(store)[i] ?? null),
};

beforeEach(() => {
	Object.defineProperty(globalThis, "localStorage", {
		value: mockStorage,
		writable: true,
		configurable: true,
	});
});

describe("useTheme", () => {
	beforeEach(() => {
		mockStorage.clear();
		vi.clearAllMocks();
		document.documentElement.removeAttribute("data-theme");
		document.documentElement.removeAttribute("data-mode");
		document.documentElement.removeAttribute("data-density");
	});

	afterEach(() => {
		mockStorage.clear();
	});

	it("defaults to ember theme", () => {
		const { result } = renderHook(() => useTheme());
		expect(result.current.theme).toBe("ember");
	});

	it("defaults to comfortable density", () => {
		const { result } = renderHook(() => useTheme());
		expect(result.current.density).toBe("comfortable");
	});

	it("reads theme from localStorage", () => {
		store.beats_theme = "midnight";
		const { result } = renderHook(() => useTheme());
		expect(result.current.theme).toBe("midnight");
	});

	it("reads density from localStorage", () => {
		store.beats_density = "compact";
		const { result } = renderHook(() => useTheme());
		expect(result.current.density).toBe("compact");
	});

	it("persists theme to localStorage on change", () => {
		const { result } = renderHook(() => useTheme());
		act(() => result.current.setTheme("forest"));
		expect(mockStorage.setItem).toHaveBeenCalledWith("beats_theme", "forest");
	});

	it("persists density to localStorage on change", () => {
		const { result } = renderHook(() => useTheme());
		act(() => result.current.setDensity("spacious"));
		expect(mockStorage.setItem).toHaveBeenCalledWith("beats_density", "spacious");
	});

	it("applies data-theme attribute on <html>", () => {
		const { result } = renderHook(() => useTheme());
		act(() => result.current.setTheme("sunset"));
		expect(document.documentElement.getAttribute("data-theme")).toBe("sunset");
	});

	it("applies data-density attribute on <html>", () => {
		const { result } = renderHook(() => useTheme());
		act(() => result.current.setDensity("compact"));
		expect(document.documentElement.getAttribute("data-density")).toBe("compact");
	});

	it("updates state when theme changes", () => {
		const { result } = renderHook(() => useTheme());
		act(() => result.current.setTheme("mono"));
		expect(result.current.theme).toBe("mono");
	});

	it("updates state when density changes", () => {
		const { result } = renderHook(() => useTheme());
		act(() => result.current.setDensity("spacious"));
		expect(result.current.density).toBe("spacious");
	});

	it("defaults to dark mode", () => {
		const { result } = renderHook(() => useTheme());
		expect(result.current.mode).toBe("dark");
	});

	it("reads mode from localStorage", () => {
		store.beats_mode = "light";
		const { result } = renderHook(() => useTheme());
		expect(result.current.mode).toBe("light");
	});

	it("persists mode to localStorage on change", () => {
		const { result } = renderHook(() => useTheme());
		act(() => result.current.setMode("light"));
		expect(mockStorage.setItem).toHaveBeenCalledWith("beats_mode", "light");
	});

	it("applies data-mode attribute on <html>", () => {
		const { result } = renderHook(() => useTheme());
		act(() => result.current.setMode("light"));
		expect(document.documentElement.getAttribute("data-mode")).toBe("light");
	});

	it("updates state when mode changes", () => {
		const { result } = renderHook(() => useTheme());
		act(() => result.current.setMode("light"));
		expect(result.current.mode).toBe("light");
	});
});
