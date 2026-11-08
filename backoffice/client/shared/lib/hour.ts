/**
 * The hour the back office is drawn in: afternoon, dusk, or whichever the
 * system is on. tokens.css does the drawing off `data-theme`; index.html
 * repeats the key, so a stored hour is on the page before first paint.
 */

export type Hour = "afternoon" | "dusk" | "system";

const KEY = "backoffice_hour";

export function readHour(): Hour {
	try {
		const stored = localStorage.getItem(KEY);
		return stored === "afternoon" || stored === "dusk" ? stored : "system";
	} catch {
		return "system";
	}
}

export function applyHour(hour: Hour): void {
	const root = document.documentElement;
	if (hour === "system") root.removeAttribute("data-theme");
	else root.setAttribute("data-theme", hour);
	try {
		if (hour === "system") localStorage.removeItem(KEY);
		else localStorage.setItem(KEY, hour);
	} catch {
		// A private window can refuse storage; the page has still changed.
	}
}
