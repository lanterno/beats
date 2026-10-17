/**
 * Money typed into a rate field, and money the API sent back. A rate is
 * read off the string, digit by digit, into the integer minor units the
 * API stores; a fraction finer than the currency's is refused, never
 * rounded, since a rate the user did not write is a rate they did not
 * agree to. `minorUnits` is always the API's, from its currency table.
 */
import { describe, expect, it } from "vitest";
import { formatMoney, formatRate, minorToInput, parseMoney } from "./money";

const EUR = 2;
const JPY = 0;
const KWD = 3;

const minor = (text: string, minorUnits = EUR) => {
	const parsed = parseMoney(text, minorUnits);
	return parsed.ok ? parsed.minor : null;
};

describe("parseMoney", () => {
	it("reads whole and fractional amounts into minor units", () => {
		expect(minor("85")).toBe(8500);
		expect(minor("85.5")).toBe(8550);
		expect(minor("85.50")).toBe(8550);
		expect(minor(" 85.50 ")).toBe(8550);
	});

	it("takes a comma as the decimal separator too", () => {
		expect(minor("85,50")).toBe(8550);
	});

	it("refuses more fraction digits than the currency has, rather than rounding", () => {
		expect(minor("85.505", EUR)).toBeNull();
		expect(minor("85.505", KWD)).toBe(85505);
		expect(minor("5000", JPY)).toBe(5000);
		expect(minor("85.5", JPY)).toBeNull();
	});

	it("refuses a comma before three digits, which reads either way", () => {
		// The Iraqi dinar has three decimals, as KWD does, and 25,000 dinars
		// is an hour's rate there: read as 25.000 it would be saved a
		// thousand times too low.
		expect(minor("25,000", KWD)).toBeNull();
		expect(minor("1,500", KWD)).toBeNull();
		expect(minor("1,500", JPY)).toBeNull();
		expect(minor("25.000", KWD)).toBe(25000);
		expect(minor("25000", KWD)).toBe(25_000_000);
		expect(minor("85,5", KWD)).toBe(85500);
		const parsed = parseMoney("25,000", KWD);
		if (!parsed.ok) expect(parsed.reason).toMatch(/thousands/);
	});

	it("refuses thousands separators and signs", () => {
		expect(minor("1,000.00")).toBeNull();
		expect(minor("1 000")).toBeNull();
		expect(minor("-5")).toBeNull();
		expect(minor("+5")).toBeNull();
	});

	it("refuses nothing, zero, and more than the API takes", () => {
		expect(minor("")).toBeNull();
		expect(minor("   ")).toBeNull();
		expect(minor("0")).toBeNull();
		expect(minor("0.00")).toBeNull();
		expect(minor("1000000")).toBe(100_000_000);
		expect(minor("1000000.01")).toBeNull();
		expect(minor("99999999999999999999")).toBeNull();
	});

	it("says why it refused", () => {
		const parsed = parseMoney("85.505", EUR);
		expect(parsed.ok).toBe(false);
		if (!parsed.ok) expect(parsed.reason).toMatch(/2 digits/);
	});
});

describe("formatMoney", () => {
	it("shows as many decimals as the currency has, whatever the browser thinks", () => {
		expect(formatMoney(6650, "JPY", JPY)).toBe("¥6,650");
		expect(formatMoney(352750, "EUR", EUR)).toBe("€3,527.50");
		expect(formatMoney(16419, "KWD", KWD)).toMatch(/16\.419$/);
	});

	it("puts a rate per hour", () => {
		expect(formatRate(8500, "EUR", EUR)).toBe("€85.00/h");
	});
});

describe("minorToInput", () => {
	// A stored rate opens in its field as text parseMoney reads back to the
	// same minor units: an edit that changes nothing must send nothing new.
	it("writes a stored rate as the text that reads back to it", () => {
		for (const [rate, minorUnits, text] of [
			[8550, EUR, "85.50"],
			[5, EUR, "0.05"],
			[100_000_000, EUR, "1000000.00"],
			[6650, JPY, "6650"],
			[16419, KWD, "16.419"],
			[7, KWD, "0.007"],
		] as const) {
			expect(minorToInput(rate, minorUnits)).toBe(text);
			expect(minor(text, minorUnits)).toBe(rate);
		}
	});
});
