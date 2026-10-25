/**
 * The record page over one member's slice: the entries as rows, the
 * balance as a sentence, and — since the component is parameterised by
 * the read — the same page says who may read it when the read is refused.
 */
import type { UseQueryResult } from "@tanstack/react-query";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { OrgRecord } from "@/entities/organisation";
import { ApiError } from "@/shared/api";
import { RecordPage } from "./RecordPage";

const RECORD: OrgRecord = {
	organisation: { id: "o1", name: "Acme" },
	month: "2026-10",
	first: "2026-10-01",
	last: "2026-10-24",
	projects: [
		{
			project: { id: "p1", name: "Payroll", archived: false, kind: "day_job", color: "#4E93E3" },
			members: [
				{
					userId: "u1",
					name: "Ada",
					sharedFrom: "2026-03-03T23:00:00Z",
					active: true,
					hours: 12.5,
					entries: [
						{
							id: "e1",
							day: "2026-10-02",
							start: "2026-10-02T08:00:00Z",
							end: "2026-10-02T12:30:00Z",
							hours: 4.5,
							note: "Month end",
						},
						{
							id: "e2",
							day: "2026-10-03",
							start: "2026-10-03T07:00:00Z",
							end: "2026-10-03T15:00:00Z",
							hours: 8,
						},
					],
					absences: [{ date: "2026-10-06", type: "vacation", halfDay: true }],
					hasContract: true,
					balance: {
						asOf: "2026-10-24",
						balance: 4.5,
						opening: 0,
						worked: 100,
						expectedThrough: 95.5,
						adjusted: 0,
					},
					totals: { entries: 40, hours: 300, first: "2026-03-04", last: "2026-10-03" },
				},
			],
		},
	],
};

function asQuery(result: { data?: OrgRecord; error?: unknown }) {
	return () =>
		({ data: result.data, error: result.error ?? null }) as unknown as UseQueryResult<OrgRecord>;
}

function renderPage(variant: "record" | "visible", result: { data?: OrgRecord; error?: unknown }) {
	render(
		<QueryClientProvider client={new QueryClient()}>
			<MemoryRouter initialEntries={[`/organisations/o1/${variant}`]}>
				<Routes>
					<Route
						path="/organisations/:id/:view"
						element={<RecordPage variant={variant} useRecord={asQuery(result)} />}
					/>
				</Routes>
			</MemoryRouter>
		</QueryClientProvider>,
	);
}

afterEach(cleanup);

describe("RecordPage", () => {
	it("draws a member's entries as rows, with the balance as a sentence", () => {
		renderPage("record", { data: RECORD });

		expect(screen.getByRole("heading", { name: "Acme's record" })).toBeInTheDocument();
		const ada = screen.getByRole("region", { name: "Ada" });
		const table = within(ada).getByRole("table", { name: "Entries on Payroll for Ada" });
		// A header row and one per entry.
		expect(within(table).getAllByRole("row")).toHaveLength(3);
		expect(table).toHaveTextContent("Month end");
		expect(ada).toHaveTextContent("Balance +4.5 h over");
		expect(ada).toHaveTextContent("half day");
	});

	it("on /visible, says whose data this is", () => {
		renderPage("visible", { data: RECORD });
		expect(screen.getByRole("heading", { name: "What Acme sees" })).toBeInTheDocument();
		expect(
			screen.getByText(/This is the data Acme holds about you, read through the same query/),
		).toBeInTheDocument();
	});

	it("tells a member who may read the record when the read is refused", () => {
		renderPage("record", { error: new ApiError(403, "Admins only") });
		expect(screen.getByRole("alert")).toHaveTextContent(
			"Owners, admins, managers and viewers only.",
		);
	});
});
