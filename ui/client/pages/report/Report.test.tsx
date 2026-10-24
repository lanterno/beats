/**
 * The page a client opens at `/r/:token` (docs/billing.md, phase 1c).
 *
 * What is worth pinning here is what the link's two flags do to the page,
 * since getting either wrong shows a client something its owner chose to
 * withhold, and the one message every failed link gets — the API answers a
 * single 404 for "never existed" and "revoked yesterday" alike, and the
 * page must not undo that by saying which.
 *
 * `useReport` is mocked: the real hook is a thin `useQuery` over
 * `fetchReport`, and what it returns is the API's, covered by
 * `TestReportLinksAPI` against a real database.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Report as ReportData } from "@/entities/billing";
import Report from "./Report";

const { state } = vi.hoisted(() => ({
	state: {
		report: { data: undefined, isLoading: false, isError: false } as Record<string, unknown>,
	},
}));

vi.mock("@/entities/billing", async () => {
	const actual = await vi.importActual<typeof import("@/entities/billing")>("@/entities/billing");
	return { ...actual, useReport: () => state.report };
});

const OCTOBER: ReportData = {
	clientName: "Studio Kite",
	first: "2026-10-01",
	last: "2026-10-31",
	showAmounts: true,
	showEntries: true,
	currency: "EUR",
	minorUnits: 2,
	billableHours: 30,
	unpricedHours: 0,
	amountMinor: 255000,
	lines: [
		{
			projectName: "Website",
			first: "2026-10-01",
			last: "2026-10-14",
			hours: 30,
			rateMinor: 8500,
			amountMinor: 255000,
		},
	],
	entries: [
		{ day: "2026-10-02", start: "2026-10-02T09:00:00Z", end: "2026-10-02T11:30:00Z", hours: 2.5 },
	],
};

function renderWith(query: Record<string, unknown>) {
	state.report = { data: undefined, isLoading: false, isError: false, ...query };
	render(
		<MemoryRouter initialEntries={["/r/sometoken"]}>
			<Routes>
				<Route path="/r/:token" element={<Report />} />
			</Routes>
		</MemoryRouter>,
	);
}

/** The page as a client sees it, over OCTOBER with these fields replaced. */
function renderReport(report: Partial<ReportData> = {}) {
	renderWith({ data: { ...OCTOBER, ...report } });
}

afterEach(cleanup);

describe("Report", () => {
	it("shows the client's hours and what they come to", () => {
		renderReport();

		expect(screen.getByRole("heading", { name: "Studio Kite" })).toBeInTheDocument();
		const total = screen.getByRole("region", { name: "Total" });
		expect(total).toHaveTextContent("30 h");
		expect(total).toHaveTextContent("€2,550.00");
		expect(screen.getByRole("region", { name: "Work" })).toHaveTextContent("Website");
	});

	it("shows hours and no money at all when the link hides amounts", () => {
		// Every money field arrives null, as the API sends them, and no
		// column of rates or amounts is drawn.
		renderReport({
			showAmounts: false,
			currency: undefined,
			minorUnits: undefined,
			unpricedHours: undefined,
			amountMinor: undefined,
			lines: [
				{
					projectName: "Website",
					first: "2026-10-01",
					last: "2026-10-14",
					hours: 30,
					rateMinor: undefined,
					amountMinor: undefined,
				},
			],
		});

		expect(screen.getByRole("region", { name: "Total" })).toHaveTextContent("30 h");
		expect(screen.queryByText(/€/)).not.toBeInTheDocument();
		const work = screen.getByRole("region", { name: "Work" });
		expect(within(work).queryByRole("columnheader", { name: "Rate" })).not.toBeInTheDocument();
		expect(within(work).queryByRole("columnheader", { name: "Amount" })).not.toBeInTheDocument();
	});

	it("draws no entries block when the link hides entries", () => {
		renderReport({ showEntries: false, entries: [] });

		expect(screen.queryByRole("region", { name: "Entries" })).not.toBeInTheDocument();
		// The lines and the total are still there: the two flags are independent.
		expect(screen.getByRole("region", { name: "Work" })).toBeInTheDocument();
		expect(screen.getByRole("region", { name: "Total" })).toHaveTextContent("30 h");
	});

	it("says one thing for every way a link fails, and names no reason", () => {
		renderWith({ isError: true });

		expect(
			screen.getByRole("heading", { name: "This report link is no longer available" }),
		).toBeInTheDocument();
		// Not "revoked", not "expired", not "no such link": the API answers
		// one 404 for all of them so a reader cannot tell them apart.
		expect(screen.queryByText(/Studio Kite/)).not.toBeInTheDocument();
	});
});
