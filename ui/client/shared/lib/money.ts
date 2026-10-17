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

// Digits, then optionally one "." or "," and the digits after it. Nothing
// else: no sign, no thousands separator, no currency symbol.
const AMOUNT = /^(\d+)(?:([.,])(\d+))?$/;

/**
 * A rate typed into a field, in minor units. Read off the string, never
 * through `parseFloat`, so 0.1 + 0.2 never reaches a rate. The decimal
 * separator is "." or ","; more fraction digits than the currency has are
 * refused, never rounded, and so are thousands separators ("1,000.00"),
 * signs, zero, and anything over `RATE_MINOR_MAX` — what the API would
 * answer 422 for. A "," before exactly three digits is refused too, in
 * every currency: "25,000" is twenty-five thousand to one reader and 25.000
 * to another, and in a currency with three decimals (IQD, KWD) both parse.
 */
export function parseMoney(text: string, minorUnits: number): ParsedMoney {
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
	if (fraction.length > minorUnits) {
		return {
			ok: false,
			reason:
				minorUnits === 0
					? "This currency has no fraction: use a whole amount."
					: `At most ${minorUnits} digits after the separator.`,
		};
	}
	const max = RATE_MINOR_MAX / 10 ** minorUnits;
	const tooLarge = `At most ${max.toLocaleString("en-US", { minimumFractionDigits: minorUnits })}.`;
	// Past this many digits the whole part alone is over the cap, and
	// Number would start to lose them.
	if (whole.replace(/^0+/, "").length > 15) return { ok: false, reason: tooLarge };
	const minor = Number(whole) * 10 ** minorUnits + Number(fraction.padEnd(minorUnits, "0") || "0");
	if (minor === 0) return { ok: false, reason: "An amount is more than zero." };
	if (minor > RATE_MINOR_MAX) return { ok: false, reason: tooLarge };
	return { ok: true, minor };
}
