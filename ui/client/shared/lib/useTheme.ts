/**
 * Theme hook — manages the hour (afternoon / dusk), the layout density, and
 * the page layout (separate boxes, or one sheet per page). Persists to
 * localStorage, applies data attributes on <html>, and keeps the browser
 * chrome's `theme-color` on the sky.
 */
import { useCallback, useEffect, useState } from "react";

export type ThemeName = "afternoon" | "dusk";
export type Density = "comfortable" | "compact" | "spacious";
export type PageLayout = "boxes" | "sheet";

const THEME_KEY = "beats_theme";
const DENSITY_KEY = "beats_density";
const LAYOUT_KEY = "beats_layout";

/**
 * `sky` is the top of each hour's sky: what the browser paints its own
 * chrome (`theme-color`) and the swatch Settings shows. index.html stamps
 * the same values before first paint so a stored dusk does not flash.
 */
export const THEMES: { id: ThemeName; label: string; sky: string }[] = [
	{ id: "afternoon", label: "Afternoon", sky: "#7FB4D8" },
	{ id: "dusk", label: "Dusk", sky: "#1A2446" },
];

export const DENSITIES: { id: Density; label: string }[] = [
	{ id: "comfortable", label: "Comfortable" },
	{ id: "compact", label: "Compact" },
	{ id: "spacious", label: "Spacious" },
];

/**
 * Boxes is a panel per section floating on the sky; the sheet is one card
 * per page whose sections part by hairlines (the `page-sheet` rules in
 * global.css).
 */
export const LAYOUTS: { id: PageLayout; label: string }[] = [
	{ id: "boxes", label: "Boxes" },
	{ id: "sheet", label: "One sheet" },
];

/**
 * Read a stored choice, falling back when it is missing or not one of the
 * offered ids — localStorage holds whatever was last written to it. Nothing
 * is written back until the user picks.
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

function applyLayout(layout: PageLayout) {
	document.documentElement.setAttribute("data-layout", layout);
}

export function useTheme() {
	const [theme, setThemeState] = useState<ThemeName>(() =>
		getStored(THEME_KEY, THEMES, "afternoon"),
	);
	const [density, setDensityState] = useState<Density>(() =>
		getStored(DENSITY_KEY, DENSITIES, "comfortable"),
	);
	const [layout, setLayoutState] = useState<PageLayout>(() =>
		getStored(LAYOUT_KEY, LAYOUTS, "boxes"),
	);

	useEffect(() => {
		applyTheme(theme);
	}, [theme]);

	useEffect(() => {
		applyDensity(density);
	}, [density]);

	useEffect(() => {
		applyLayout(layout);
	}, [layout]);

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

	const setLayout = useCallback((l: PageLayout) => {
		setLayoutState(l);
		localStorage.setItem(LAYOUT_KEY, l);
		applyLayout(l);
	}, []);

	return { theme, setTheme, density, setDensity, layout, setLayout };
}
