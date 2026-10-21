/**
 * The share dialog's chips stand for days and an expiry the API checks
 * against the link's own zone: the ranges must be finished days, the month
 * edges must land on the right side of a new year and a short February, and
 * the longest expiry must stay inside the API's 366 days even from a leap
 * day. And the list's "Not on this link" must name what the client is
 * billed for and the link leaves out, nothing more.
 */
import { describe, expect, it } from "vitest";
import { expiryFor, notOnLink, rangeFor, reportUrl, todayIn } from "./choices";
import type { ReportLink } from "./types";

const LINK: ReportLink = {
	id: "l1",
	clientId: "c1",
	first: "2026-09-01",
	last: "2026-09-30",
	tz: "Europe/Berlin",
	showAmounts: false,
	showNotes: false,
	projects: [{ id: "a", name: "Website" }],
	expiresOn: "2026-11-17",
	createdAt: "2026-10-18T10:00:00Z",
	state: "live",
};

describe("rangeFor", () => {
	it("last month is its 1st to its last day", () => {
		expect(rangeFor("last-month", "2026-10-18")).toEqual({
			first: "2026-09-01",
			last: "2026-09-30",
		});
		expect(rangeFor("last-month", "2026-03-31")).toEqual({
			first: "2026-02-01",
			last: "2026-02-28",
		});
	});

	it("the last three months reach back over a new year", () => {
		expect(rangeFor("last-3-months", "2026-01-15")).toEqual({
			first: "2025-10-01",
			last: "2025-12-31",
		});
	});

	it("this month runs to yesterday, and is no range on the 1st", () => {
		expect(rangeFor("this-month", "2026-10-18")).toEqual({
			first: "2026-10-01",
			last: "2026-10-17",
		});
		expect(rangeFor("this-month", "2026-10-01")).toBeNull();
	});
});

describe("expiryFor", () => {
	it("counts whole days from today", () => {
		expect(expiryFor(30, "2026-10-18")).toBe("2026-11-17");
	});

	it("a year from a leap day stays inside the API's 366 days", () => {
		expect(expiryFor(365, "2028-02-29")).toBe("2029-02-28");
	});
});

describe("todayIn", () => {
	it("is the day in the link's zone, not the browser's", () => {
		const lateEvening = new Date("2026-10-18T23:30:00Z");
		expect(todayIn("Europe/Berlin", lateEvening)).toBe("2026-10-19");
		expect(todayIn("America/Los_Angeles", lateEvening)).toBe("2026-10-18");
	});
});

describe("reportUrl", () => {
	it("is the SPA's own origin, /report, and the token after the #", () => {
		expect(reportUrl("http://localhost:8080", "lpr_t")).toBe("http://localhost:8080/report#lpr_t");
	});
});

describe("notOnLink", () => {
	it("names the billed projects the link leaves out", () => {
		const names = new Map([
			["a", "Website"],
			["b", "Logo"],
		]);
		expect(notOnLink(LINK, ["a", "b"], names)).toEqual(["Logo"]);
	});

	it("leaves out a project the link names that is no longer billed", () => {
		const link = {
			...LINK,
			projects: [
				{ id: "a", name: "Website" },
				{ id: "c", name: "Old" },
			],
		};
		expect(notOnLink(link, ["a"], new Map([["a", "Website"]]))).toEqual([]);
	});
});
