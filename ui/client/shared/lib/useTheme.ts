/**
 * Theme hook — manages the hour (afternoon / dusk) and layout density.
 * Persists to localStorage, applies data attributes on <html>, and keeps
 * the browser chrome's `theme-color` on the sky.
 */
import { useCallback, useEffect, useState } from "react";

export type ThemeName = "afternoon" | "dusk";
export type Density = "comfortable" | "compact" | "spacious";

const THEME_KEY = "beats_theme";
const DENSITY_KEY = "beats_density";

/**
 * `sky` is the top of each hour's sky: what the browser paints its own
 * chrome (`theme-color`) and the swatch Settings shows. index.html stamps
 * the same values before first paint so a stored dusk does not flash.
 */
export const THEMES: { id: ThemeName; label: string; sky: string }[] = [
	{ id: "afternoon", label: "Afternoon", sky: "#8CC1E2" },
	{ id: "dusk", label: "Dusk", sky: "#1A2446" },
];

export const DENSITIES: { id: Density; label: string }[] = [
	{ id: "comfortable", label: "Comfortable" },
	{ id: "compact", label: "Compact" },
	{ id: "spacious", label: "Spacious" },
];

/**
 * Read a stored choice, falling back when it is missing or not one of the
 * offered ids. A value from before the two hours ("ember", "midnight", …)
 * reads as the fallback; nothing is written back until the user picks.
 */
function getStored<T extends string>(key: string, offered: readonly { id: T }[], fallback: T): T {
	try {
		const val = localStorage.getItem(key);
		return offered.some((o) => o.id === val) ? (val as T) : fallback;
	} catch {
		return fallback;
	}
}

function applyTheme(theme: ThemeName) {
	document.documentElement.setAttribute("data-theme", theme);
	const sky = THEMES.find((t) => t.id === theme)?.sky;
	if (sky) document.querySelector('meta[name="theme-color"]')?.setAttribute("content", sky);
}

function applyDensity(density: Density) {
	document.documentElement.setAttribute("data-density", density);
}

export function useTheme() {
	const [theme, setThemeState] = useState<ThemeName>(() =>
		getStored(THEME_KEY, THEMES, "afternoon"),
	);
	const [density, setDensityState] = useState<Density>(() =>
		getStored(DENSITY_KEY, DENSITIES, "comfortable"),
	);

	useEffect(() => {
		applyTheme(theme);
	}, [theme]);

	useEffect(() => {
		applyDensity(density);
	}, [density]);

	const setTheme = useCallback((t: ThemeName) => {
		setThemeState(t);
		localStorage.setItem(THEME_KEY, t);
		applyTheme(t);
	}, []);

	const setDensity = useCallback((d: Density) => {
		setDensityState(d);
		localStorage.setItem(DENSITY_KEY, d);
		applyDensity(d);
	}, []);

	return { theme, setTheme, density, setDensity };
}
