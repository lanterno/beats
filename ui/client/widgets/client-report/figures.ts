/**
 * The words and figures of a public report, worked out from the API's
 * numbers and dates and nothing else: nothing here prices or rounds anew.
 *
 * Dates are the API's 'YYYY-MM-DD' strings, read with `parseIsoDate` (local
 * noon), never `new Date("2026-09-01")`, which is UTC midnight and prints
 * 31 August west of Greenwich. They are written day first, "15 September
 * 2026", in English, as the rest of the page (plan decision 29); the money is
 * `formatMoney`'s en-US, as on the Clients page, so the preview reads as the
 * invoice does.
 */
import { parseIsoDate } from "@/shared/lib/date";
import { formatMoney, formatRate } from "@/shared/lib/money";
import type { PricedLine, ReportMoney } from "@/shared/report";

/** "30.00": an API figure to the hundredth, as the invoice prints it. */
export function hoursFixed(hours: number): string {
	return hours.toFixed(2);
}

function parts(iso: string): { day: number; month: string; year: number } | null {
	const d = parseIsoDate(iso);
	if (!d) return null;
	return {
		day: d.getDate(),
		month: d.toLocaleDateString("en-US", { month: "long" }),
		year: d.getFullYear(),
	};
}

/** "15 September 2026". */
export function dateText(iso: string): string {
	const p = parts(iso);
	return p ? `${p.day} ${p.month} ${p.year}` : iso;
}

/** "October 2026", from the API's "2026-10". */
export function monthHeading(month: string): string {
	const p = parts(`${month}-01`);
	return p ? `${p.month} ${p.year}` : month;
}

/**
 * "1–30 September 2026", "15 September – 31 October 2026",
 * "15 December 2025 – 31 January 2026", or the one day.
 */
export function rangeText(first: string, last: string): string {
	const a = parts(first);
	const b = parts(last);
	if (!a || !b) return `${first} – ${last}`;
	if (first === last) return dateText(first);
	if (a.year !== b.year) return `${dateText(first)} – ${dateText(last)}`;
	if (a.month !== b.month) return `${a.day} ${a.month} – ${b.day} ${b.month} ${b.year}`;
	return `${a.day}–${b.day} ${b.month} ${b.year}`;
}

/** "between 15 September and 31 October 2026", or "on 15 September 2026". */
export function betweenText(first: string, last: string): string {
	const a = parts(first);
	const b = parts(last);
	if (!a || !b) return `between ${first} and ${last}`;
	if (first === last) return `on ${dateText(first)}`;
	if (a.year !== b.year) return `between ${dateText(first)} and ${dateText(last)}`;
	return `between ${a.day} ${a.month} and ${dateText(last)}`;
}

/** "15–30 Sep", a line's run of days, short; or the one day. */
export function runText(first: string, last: string): string {
	const a = parseIsoDate(first);
	const b = parseIsoDate(last);
	if (!a || !b) return `${first} – ${last}`;
	const short = (d: Date) => d.toLocaleDateString("en-US", { month: "short" });
	if (first === last) return `${a.getDate()} ${short(a)}`;
	if (short(a) === short(b) && a.getFullYear() === b.getFullYear()) {
		return `${a.getDate()}–${b.getDate()} ${short(b)}`;
	}
	return `${a.getDate()} ${short(a)} – ${b.getDate()} ${short(b)}`;
}

/** "Wed 16 Sep", a day row's day. */
export function dayText(iso: string): string {
	const d = parseIsoDate(iso);
	if (!d) return iso;
	const weekday = d.toLocaleDateString("en-US", { weekday: "short" });
	return `${weekday} ${d.getDate()} ${d.toLocaleDateString("en-US", { month: "short" })}`;
}

/**
 * "euros", "US dollars": the currency's name as an amount of it is spoken,
 * for "Amounts in euros (EUR)". The code alone where the browser has no name.
 */
export function currencyName(currency: string): string {
	try {
		const name = new Intl.NumberFormat("en-US", {
			style: "currency",
			currency,
			currencyDisplay: "name",
		})
			.formatToParts(2)
			.find((part) => part.type === "currency")?.value;
		return name ?? currency;
	} catch {
		return currency;
	}
}

/**
 * A priced line's arithmetic, in the pieces a phone stacks:
 * ["30.00 h × €85.00/h", "= €2,550.00"], or ["12.00 h · no rate set"] for a
 * line with no rate, never a zero.
 */
export function lineArithmetic(line: PricedLine, money: ReportMoney): string[] {
	const hours = `${hoursFixed(line.hours)} h`;
	if (line.rate_minor === null || line.amount_minor === null) return [`${hours} · no rate set`];
	const { currency, minor_units: minorUnits } = money;
	return [
		`${hours} × ${formatRate(line.rate_minor, currency, minorUnits)}`,
		`= ${formatMoney(line.amount_minor, currency, minorUnits)}`,
	];
}

/**
 * The amount beside a total: "€6,077.50", "€2,550.00, plus 12.00 h with no
 * rate set", or "no rate set" when nothing in it is priced.
 */
export function amountText(
	amountMinor: number,
	unpricedHours: number,
	billableHours: number,
	money: ReportMoney,
): string {
	if (unpricedHours > 0 && unpricedHours >= billableHours) return "no rate set";
	const amount = formatMoney(amountMinor, money.currency, money.minor_units);
	return unpricedHours > 0
		? `${amount}, plus ${hoursFixed(unpricedHours)} h with no rate set`
		: amount;
}
