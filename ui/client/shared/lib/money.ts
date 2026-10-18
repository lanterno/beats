/**
 * Money, as the API keeps it: integer minor units of one ISO 4217 currency
 * (cents for EUR, yen for JPY, fils for KWD), with the currency's minor
 * units sent beside every amount (docs/billing.md). `minorUnits` always
 * comes from the API's table, never from the browser's ICU, which disagrees
 * with ISO for some codes (HUF among them). Nothing here prices anything:
 * every amount is the API's, and this only shows it or reads a rate typed in.
 */

/** The API's `RATE_MINOR_MAX` (`domain/models.py`): 1,000,000.00 an hour at two decimals. */
export const RATE_MINOR_MAX = 100_000_000;

/**
 * "€3,527.50", "¥6,650", "KWD 16.419": `minor` in its currency, with exactly
 * `minorUnits` decimals. `minor / 10 ** minorUnits` is exact for display at
 * every amount the API can send (at most 2^53 minor units). en-US, as the
 * hours helpers are.
 */
export function formatMoney(minor: number, currency: string, minorUnits: number): string {
	return new Intl.NumberFormat("en-US", {
		style: "currency",
		currency,
		minimumFractionDigits: minorUnits,
		maximumFractionDigits: minorUnits,
	}).format(minor / 10 ** minorUnits);
}

/** "€85.00/h": a rate per hour in minor units. */
export function formatRate(rateMinor: number, currency: string, minorUnits: number): string {
	return `${formatMoney(rateMinor, currency, minorUnits)}/h`;
}

/**
 * "85.50", "6650", "16.419": minor units as a rate field starts when it edits
 * one, the inverse of `parseMoney` — digits and a "." only, no symbol and no
 * thousands separator, so the field reads back to the same amount.
 */
export function minorToInput(minor: number, minorUnits: number): string {
	if (minorUnits === 0) return String(minor);
	const digits = String(minor).padStart(minorUnits + 1, "0");
	return `${digits.slice(0, -minorUnits)}.${digits.slice(-minorUnits)}`;
}

export type ParsedMoney = { ok: true; minor: number } | { ok: false; reason: string };

/** An amount read off a field, in whole units of its last decimal place. */
export type ParsedAmount = { ok: true; units: number } | { ok: false; reason: string };

/** The sentences `parseAmount` gives that depend on what is being typed. */
export interface AmountMessages {
	/** With no decimal places, a fraction was typed. */
	wholeOnly?: string;
}

// Digits, then optionally one "." or "," and the digits after it. Nothing
// else: no sign, no thousands separator, no currency symbol.
const AMOUNT = /^(\d+)(?:([.,])(\d+))?$/;

/**
 * An amount typed into a field, as an integer count of its smallest step:
 * hundredths at two `places`, whole units at none. Read off the string,
 * never through `parseFloat`, so 0.1 + 0.2 never reaches a figure. The
 * decimal separator is "." or ","; more fraction digits than `places` are
 * refused, never rounded, and so are thousands separators ("1,000.00"),
 * signs, zero, and anything over `max` (in the same units) — what the API
 * would answer 422 for. A "," before exactly three digits is refused too,
 * at every `places`: "25,000" is twenty-five thousand to one reader and
 * 25.000 to another, and with three places (IQD, KWD) both parse.
 */
export function parseAmount(
	text: string,
	places: number,
	max: number,
	messages: AmountMessages = {},
): ParsedAmount {
	const trimmed = text.trim();
	if (trimmed === "") return { ok: false, reason: "Enter an amount." };
	const match = AMOUNT.exec(trimmed);
	if (!match) {
		return {
			ok: false,
			reason: "Use digits, with one . or , before the fraction, and no thousands separator.",
		};
	}
	const [, whole, separator, fraction = ""] = match;
	if (separator === "," && fraction.length === 3) {
		return {
			ok: false,
			reason: `"${trimmed}" could have a thousands separator: write it without one, with a "." before any fraction.`,
		};
	}
	if (fraction.length > places) {
		return {
			ok: false,
			reason:
				places === 0
					? (messages.wholeOnly ?? "Use a whole amount.")
					: `At most ${places} digits after the separator.`,
		};
	}
	const tooLarge = `At most ${(max / 10 ** places).toLocaleString("en-US", { minimumFractionDigits: places })}.`;
	// Past this many digits the whole part alone is over the cap, and
	// Number would start to lose them.
	if (whole.replace(/^0+/, "").length > 15) return { ok: false, reason: tooLarge };
	const units = Number(whole) * 10 ** places + Number(fraction.padEnd(places, "0") || "0");
	if (units === 0) return { ok: false, reason: "An amount is more than zero." };
	if (units > max) return { ok: false, reason: tooLarge };
	return { ok: true, units };
}

/**
 * A rate typed into a field, in minor units, through `parseAmount` at the
 * currency's `minorUnits` and capped at `RATE_MINOR_MAX`.
 */
export function parseMoney(text: string, minorUnits: number): ParsedMoney {
	const parsed = parseAmount(text, minorUnits, RATE_MINOR_MAX, {
		wholeOnly: "This currency has no fraction: use a whole amount.",
	});
	return parsed.ok ? { ok: true, minor: parsed.units } : parsed;
}
