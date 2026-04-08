/**
 * Date and time utilities
 * All date handling follows UTC-first principle: API sends UTC, we display in local timezone.
 */

/**
 * Parse an ISO string from the API as UTC (append Z if no timezone).
 * Use when the API sends UTC timestamps; ensures correct instant for comparison and local display.
 */
export function parseUtcIso(iso: string): Date {
	if (!iso || typeof iso !== "string") return new Date(NaN);
	const hasTimezone = iso.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(iso) || /[+-]\d{4}$/.test(iso);
	const normalized = hasTimezone ? iso : `${iso.replace(/\.\d+$/, "")}Z`;
	return new Date(normalized);
}

/**
 * Format a date for display in the user's local timezone (e.g., "Dec 11, 2024")
 */
export function formatDate(dateString: string): string {
	const date = parseUtcIso(dateString);
	return date.toLocaleDateString(undefined, {
		month: "short",
		day: "numeric",
		year: "numeric",
	});
}

/**
 * Format a time for display in the user's local timezone (e.g., "02:30 PM")
 */
export function formatTime(dateString: string): string {
	const date = parseUtcIso(dateString);
	return date.toLocaleTimeString(undefined, {
		hour: "2-digit",
		minute: "2-digit",
		hour12: true,
	});
}

/**
 * Format a Date as "YYYY-MM-DDTHH:mm" in local time for <input type="datetime-local">.
 */
export function toLocalDatetimeLocalString(date: Date): string {
	const y = date.getFullYear();
	const m = String(date.getMonth() + 1).padStart(2, "0");
	const d = String(date.getDate()).padStart(2, "0");
	const h = String(date.getHours()).padStart(2, "0");
	const min = String(date.getMinutes()).padStart(2, "0");
	return `${y}-${m}-${d}T${h}:${min}`;
}

/**
 * Get start and end of current week (Monday to Sunday)
 */
export function getCurrentWeekRange(): { start: Date; end: Date } {
	return getWeekRange(0);
}

/**
 * Get start (Monday 00:00) and end (Sunday 23:59:59) of a week.
 * @param weekOffset 0 = current week, -1 = last week, 1 = next week, etc.
 */
export function getWeekRange(weekOffset: number): { start: Date; end: Date } {
	const now = new Date();
	const day = now.getDay();
	const diff = now.getDate() - day + (day === 0 ? -6 : 1);
	const monday = new Date(now);
	monday.setDate(diff + weekOffset * 7);
	monday.setHours(0, 0, 0, 0);

	const sunday = new Date(monday);
	sunday.setDate(monday.getDate() + 6);
	sunday.setHours(23, 59, 59, 999);

	return { start: monday, end: sunday };
}

/**
 * Get day name from a date
 */
export function getDayName(date: Date, format: "short" | "long" = "short"): string {
	return date.toLocaleDateString("en-US", { weekday: format });
}

/**
 * Format date for short display (e.g., "Dec 11")
 */
export function formatDateShort(date: Date): string {
	return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/**
 * Get the Monday of the week that is `weeksAgo` weeks before the current week.
 */
export function getMondayOfWeeksAgo(weeksAgo: number): Date {
	const { start } = getCurrentWeekRange();
	const d = new Date(start);
	d.setDate(start.getDate() - 7 * weeksAgo);
	return d;
}

/**
 * Get ISO week number (1–53) for a date. Week starts on Monday.
 */
export function getISOWeek(date: Date): number {
	const d = new Date(date);
	d.setHours(0, 0, 0, 0);
	d.setDate(d.getDate() + 4 - (d.getDay() || 7));
	const yearStart = new Date(d.getFullYear(), 0, 1);
	return Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
}

/**
 * Get a "Week N" label for the week that is `weeksAgo` weeks before the current week.
 */
export function getWeekNumberLabel(weeksAgo: number): string {
	const monday = getMondayOfWeeksAgo(weeksAgo);
	return `Week ${getISOWeek(monday)}`;
}
