/**
 * Theme hook — manages color theme, color mode, and layout density.
 * Persists to localStorage, applies data attributes on <html>.
 */
import { useCallback, useEffect, useState } from "react";

export type ThemeName = "ember" | "midnight" | "forest" | "mono" | "sunset";
export type ColorMode = "dark" | "light";
export type Density = "comfortable" | "compact" | "spacious";

const THEME_KEY = "beats_theme";
const MODE_KEY = "beats_mode";
const DENSITY_KEY = "beats_density";

export const THEMES: { id: ThemeName; label: string; accent: string }[] = [
	{ id: "ember", label: "Ember", accent: "#d4952a" },
	{ id: "midnight", label: "Midnight", accent: "#6699cc" },
	{ id: "forest", label: "Forest", accent: "#66b366" },
	{ id: "mono", label: "Mono", accent: "#999999" },
	{ id: "sunset", label: "Sunset", accent: "#e06040" },
];

export const COLOR_MODES: { id: ColorMode; label: string }[] = [
	{ id: "dark", label: "Dark" },
	{ id: "light", label: "Light" },
];

export const DENSITIES: { id: Density; label: string }[] = [
	{ id: "comfortable", label: "Comfortable" },
	{ id: "compact", label: "Compact" },
	{ id: "spacious", label: "Spacious" },
];

function getStored<T extends string>(key: string, fallback: T): T {
	try {
		const val = localStorage.getItem(key);
		return (val as T) || fallback;
	} catch {
		return fallback;
	}
}

function applyTheme(theme: ThemeName) {
	document.documentElement.setAttribute("data-theme", theme);
}

function applyMode(mode: ColorMode) {
	document.documentElement.setAttribute("data-mode", mode);
}

function applyDensity(density: Density) {
	document.documentElement.setAttribute("data-density", density);
}

export function useTheme() {
	const [theme, setThemeState] = useState<ThemeName>(() => getStored(THEME_KEY, "ember"));
	const [mode, setModeState] = useState<ColorMode>(() => getStored(MODE_KEY, "dark"));
	const [density, setDensityState] = useState<Density>(() => getStored(DENSITY_KEY, "comfortable"));

	useEffect(() => {
		applyTheme(theme);
	}, [theme]);

	useEffect(() => {
		applyMode(mode);
	}, [mode]);

	useEffect(() => {
		applyDensity(density);
	}, [density]);

	const setTheme = useCallback((t: ThemeName) => {
		setThemeState(t);
		localStorage.setItem(THEME_KEY, t);
		applyTheme(t);
	}, []);

	const setMode = useCallback((m: ColorMode) => {
		setModeState(m);
		localStorage.setItem(MODE_KEY, m);
		applyMode(m);
	}, []);

	const setDensity = useCallback((d: Density) => {
		setDensityState(d);
		localStorage.setItem(DENSITY_KEY, d);
		applyDensity(d);
	}, []);

	return { theme, setTheme, mode, setMode, density, setDensity };
}
