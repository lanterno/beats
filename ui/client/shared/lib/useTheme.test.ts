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
		document.documentElement.removeAttribute("data-density");
		document.head.querySelector('meta[name="theme-color"]')?.remove();
		const meta = document.createElement("meta");
		meta.name = "theme-color";
		meta.content = "";
		document.head.appendChild(meta);
	});

	afterEach(() => {
		mockStorage.clear();
	});

	it("defaults to the afternoon", () => {
		const { result } = renderHook(() => useTheme());
		expect(result.current.theme).toBe("afternoon");
		expect(document.documentElement.getAttribute("data-theme")).toBe("afternoon");
	});

	it("reads dusk from localStorage", () => {
		store.beats_theme = "dusk";
		const { result } = renderHook(() => useTheme());
		expect(result.current.theme).toBe("dusk");
	});

	it("reads a theme from before the two hours as the afternoon, and writes nothing back", () => {
		store.beats_theme = "midnight";
		const { result } = renderHook(() => useTheme());
		expect(result.current.theme).toBe("afternoon");
		expect(mockStorage.setItem).not.toHaveBeenCalledWith("beats_theme", expect.anything());
		expect(store.beats_theme).toBe("midnight");
	});

	it("setTheme persists, applies data-theme and moves theme-color with the hour", () => {
		const themeColor = () =>
			document.querySelector('meta[name="theme-color"]')?.getAttribute("content");
		const { result } = renderHook(() => useTheme());
		const afternoonSky = themeColor();
		expect(afternoonSky).toBeTruthy();

		act(() => result.current.setTheme("dusk"));
		expect(result.current.theme).toBe("dusk");
		expect(mockStorage.setItem).toHaveBeenCalledWith("beats_theme", "dusk");
		expect(document.documentElement.getAttribute("data-theme")).toBe("dusk");
		expect(themeColor()).toBeTruthy();
		expect(themeColor()).not.toBe(afternoonSky);

		act(() => result.current.setTheme("afternoon"));
		expect(themeColor()).toBe(afternoonSky);
	});

	it("defaults to comfortable density", () => {
		const { result } = renderHook(() => useTheme());
		expect(result.current.density).toBe("comfortable");
	});

	it("reads density from localStorage", () => {
		store.beats_density = "compact";
		const { result } = renderHook(() => useTheme());
		expect(result.current.density).toBe("compact");
	});

	it("setDensity persists and applies data-density", () => {
		const { result } = renderHook(() => useTheme());
		act(() => result.current.setDensity("spacious"));
		expect(result.current.density).toBe("spacious");
		expect(mockStorage.setItem).toHaveBeenCalledWith("beats_density", "spacious");
		expect(document.documentElement.getAttribute("data-density")).toBe("spacious");
	});
});
