/**
 * The share dialog's choices and the links list's words, pure: the days a
 * chip stands for, the last day an expiry chip stands for, the address a
 * token is opened at, and what a link shows or leaves out.
 *
 * Every day here is a 'YYYY-MM-DD' in the link's zone, the one its days are
 * counted in and the one the API checks "finished" and "expires" against,
 * which need not be the browser's.
 */
import { addIsoDays } from "@/shared/lib";
import type { ReportLink } from "./types";

export type RangeChoice = "last-month" | "last-3-months" | "this-month";

/** How long a link opens for, in days from today. A link always ends: there is no "never". */
export type ExpiryChoice = 30 | 90 | 365;

/** Today in `tz`, as 'YYYY-MM-DD'. */
export function todayIn(tz: string, now: Date = new Date()): string {
	const parts = new Intl.DateTimeFormat("en-US", {
		timeZone: tz,
		year: "numeric",
		month: "2-digit",
		day: "2-digit",
	}).formatToParts(now);
	const part = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
	return `${part("year")}-${part("month")}-${part("day")}`;
}

/** The 1st of the month `back` months before the one `iso` is in. */
function firstOfMonthBefore(iso: string, back: number): string {
	const index = Number(iso.slice(0, 4)) * 12 + Number(iso.slice(5, 7)) - 1 - back;
	const year = Math.floor(index / 12);
	return `${String(year).padStart(4, "0")}-${String((index % 12) + 1).padStart(2, "0")}-01`;
}

/**
 * The days a chip stands for, all of them finished: the last is yesterday at
 * the latest, since a report covers finished days only. "This month to
 * yesterday" is null on the 1st, when it would hold no day.
 */
export function rangeFor(
	choice: RangeChoice,
	todayIso: string,
): { first: string; last: string } | null {
	const thisMonth = firstOfMonthBefore(todayIso, 0);
	if (choice === "this-month") {
		return todayIso === thisMonth ? null : { first: thisMonth, last: addIsoDays(todayIso, -1) };
	}
	return {
		first: firstOfMonthBefore(todayIso, choice === "last-month" ? 1 : 3),
		last: addIsoDays(thisMonth, -1),
	};
}

/** The last day a link opens: today plus the chip's days, inside the API's 366 in every year. */
export function expiryFor(days: ExpiryChoice, todayIso: string): string {
	return addIsoDays(todayIso, days);
}

/**
 * Where a token is opened: the SPA's own origin, so lifepete.com, a
 * self-hosted address and the dev server each make links to themselves.
 * The token is after the `#`, which no server or log on the way sees.
 */
export function reportUrl(origin: string, token: string): string {
	return `${origin}/report#${token}`;
}

/**
 * The client's billed projects a link leaves out, by name: ones left out
 * when it was made, and ones billed to the client since. A project the link
 * names is never listed, nor one no longer billed.
 */
export function notOnLink(
	link: ReportLink,
	billedProjectIds: Iterable<string>,
	names: ReadonlyMap<string, string>,
): string[] {
	const onLink = new Set(link.projects.map((project) => project.id));
	return [...billedProjectIds]
		.filter((id) => !onLink.has(id))
		.map((id) => names.get(id) ?? "A project")
		.sort((a, b) => a.localeCompare(b));
}

/** "Hours", "Hours and amounts", and " · with notes" when it shows them. */
export function describeShows(link: Pick<ReportLink, "showAmounts" | "showNotes">): string {
	return `${link.showAmounts ? "Hours and amounts" : "Hours"}${link.showNotes ? " · with notes" : ""}`;
}
