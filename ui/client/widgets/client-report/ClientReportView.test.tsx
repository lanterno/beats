/**
 * The report a client reads: each line's arithmetic with amounts, no money
 * anywhere without them, an unpriced line that never reads as zero, the
 * empty and partial-month sentences, and day rows folded on screen. Fixtures
 * are the API's shapes; every figure in them is the API's, and the view only
 * writes them out.
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import type { HoursReport, PricedReport } from "@/shared/report";
import { ClientReportView } from "./ClientReportView";

const TODAY = new Date(2026, 9, 18, 12);

const PRICED: PricedReport = {
	client_name: "Studio Kite",
	first: "2026-09-15",
	last: "2026-10-31",
	shows: { amounts: true, notes: true },
	billable_hours: 71.5,
	money: { currency: "EUR", minor_units: 2, amount_minor: 607_750, unpriced_hours: 0 },
	months: [
		{
			month: "2026-09",
			first: "2026-09-15",
			last: "2026-09-30",
			whole_month: false,
			billable_hours: 30,
			amount_minor: 255_000,
			unpriced_hours: 0,
			lines: [
				{
					project_name: "Website",
					first: "2026-09-15",
					last: "2026-09-30",
					hours: 30,
					rate_minor: 8500,
					amount_minor: 255_000,
				},
			],
			days: [
				{ day: "2026-09-16", project_name: "Website", hours: 2.5, notes: ["Navigation fixes"] },
			],
		},
		{
			month: "2026-10",
			first: "2026-10-01",
			last: "2026-10-31",
			whole_month: true,
			billable_hours: 41.5,
			amount_minor: 352_750,
			unpriced_hours: 0,
			lines: [
				{
					project_name: "Website",
					first: "2026-10-01",
					last: "2026-10-31",
					hours: 41.5,
					rate_minor: 8500,
					amount_minor: 352_750,
				},
			],
			days: [{ day: "2026-10-02", project_name: "Website", hours: 41.5, notes: [] }],
		},
	],
};

const HOURS: HoursReport = {
	client_name: "Studio Kite",
	first: "2026-10-01",
	last: "2026-10-31",
	shows: { amounts: false, notes: false },
	billable_hours: 41.5,
	months: [
		{
			month: "2026-10",
			first: "2026-10-01",
			last: "2026-10-31",
			whole_month: true,
			billable_hours: 41.5,
			lines: [{ project_name: "Website", hours: 41.5 }],
			days: [{ day: "2026-10-02", project_name: "Website", hours: 41.5 }],
		},
	],
};

afterEach(cleanup);

describe("ClientReportView", () => {
	it("shows each line's arithmetic with amounts", () => {
		const { container } = render(<ClientReportView report={PRICED} today={TODAY} />);
		expect(container.textContent).toContain("30.00 h × €85.00/h = €2,550.00");
		expect(container.textContent).toContain("71.50 billable hours · €6,077.50");
		expect(
			screen.getByText("Amounts in euros (EUR), before tax. Billable hours only."),
		).toBeTruthy();
	});

	it("says hours only, and no money anywhere, without amounts", () => {
		const { container } = render(<ClientReportView report={HOURS} today={TODAY} />);
		expect(screen.getByText("Hours only. Amounts are on your invoice.")).toBeTruthy();
		expect(container.textContent).toContain("41.50 h");
		expect(container.textContent).not.toContain("€");
	});

	it("an unpriced line says no rate set, never zero", () => {
		const october = PRICED.months[1];
		const report: PricedReport = {
			...PRICED,
			billable_hours: 83.5,
			money: { ...PRICED.money, unpriced_hours: 12 },
			months: [
				PRICED.months[0],
				{
					...october,
					billable_hours: 53.5,
					unpriced_hours: 12,
					lines: [
						...october.lines,
						{
							project_name: "Logo refresh",
							first: "2026-10-05",
							last: "2026-10-09",
							hours: 12,
							rate_minor: null,
							amount_minor: null,
						},
					],
				},
			],
		};
		const { container } = render(<ClientReportView report={report} today={TODAY} />);
		expect(container.textContent).toContain("12.00 h · no rate set");
		expect(container.textContent).toContain(
			"83.50 billable hours · €6,077.50, plus 12.00 h with no rate set",
		);
		expect(container.textContent).not.toContain("€0.00");
	});

	it("an empty report says so", () => {
		const report: PricedReport = {
			...PRICED,
			billable_hours: 0,
			money: { ...PRICED.money, amount_minor: 0 },
			months: PRICED.months.map((month) => ({
				...month,
				billable_hours: 0,
				amount_minor: 0,
				lines: [],
				days: [],
			})),
		};
		render(<ClientReportView report={report} today={TODAY} />);
		expect(
			screen.getByText(
				"No billable hours for Studio Kite between 15 September and 31 October 2026.",
			),
		).toBeTruthy();
	});

	it("a partial month says it is part of a month", () => {
		render(<ClientReportView report={PRICED} today={TODAY} />);
		expect(
			screen.getByRole("region", { name: "15–30 September 2026 (part of the month)" }),
		).toBeTruthy();
		expect(screen.getByRole("region", { name: "October 2026" })).toBeTruthy();
	});

	it("day rows fold and open", async () => {
		const user = userEvent.setup();
		render(<ClientReportView report={PRICED} today={TODAY} />);
		const september = screen.getByRole("region", {
			name: "15–30 September 2026 (part of the month)",
		});
		const toggle = september.querySelector("button[aria-expanded]") as HTMLButtonElement;
		const rows = document.getElementById(toggle.getAttribute("aria-controls") ?? "");
		expect(toggle).toHaveAttribute("aria-expanded", "false");
		// Folded on screen, still open in print.
		expect(rows).toHaveClass("hidden", "print:block");

		await user.click(toggle);
		expect(toggle).toHaveAttribute("aria-expanded", "true");
		expect(rows).not.toHaveClass("hidden");
		expect(rows?.textContent).toContain("Wed 16 Sep");
		expect(rows?.textContent).toContain("Navigation fixes");
	});
});
