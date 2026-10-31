/**
 * An approved sheet shows what approval froze and the way to reopen it;
 * a submitted one waits on Approve or Ask for changes. A viewer reads the
 * same list with no buttons. The names come off the row — a manager and a
 * viewer are shown this list and may not read the organisation's projects.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Timesheet } from "@/entities/organisation";
import { TimesheetsSection } from "./TimesheetsSection";

const { state, idle } = vi.hoisted(() => ({
	state: { sheets: [] as unknown[] },
	idle: () => ({ isPending: false, mutate: vi.fn(), mutateAsync: vi.fn() }),
}));

vi.mock("@/entities/organisation", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/organisation")>("@/entities/organisation");
	return {
		...actual,
		useTimesheets: () => ({ data: state.sheets, error: null }),
		// Neither list is read any more: this section's readers may not have them.
		useMembers: () => {
			throw new Error("the members are not read here");
		},
		useOrgProjects: () => {
			throw new Error("the projects are not read here");
		},
		useDecideTimesheet: idle,
		useReopenTimesheet: idle,
	};
});

function sheet(overrides: Partial<Timesheet>): Timesheet {
	return {
		id: "s1",
		projectId: "p1",
		projectName: "Backend",
		userId: "u1",
		memberName: "Nadia",
		month: "2026-09-01",
		status: "submitted",
		submittedAt: "2026-10-01T09:00:00Z",
		history: [],
		...overrides,
	};
}

function renderSection(role: "admin" | "viewer" = "admin") {
	render(
		<QueryClientProvider client={new QueryClient()}>
			<MemoryRouter>
				<TimesheetsSection organisationId="o1" role={role} userId="u-me" />
			</MemoryRouter>
		</QueryClientProvider>,
	);
}

afterEach(cleanup);

describe("TimesheetsSection", () => {
	it("renders an approved sheet's frozen figures and a Reopen button for an admin", () => {
		state.sheets = [
			sheet({
				id: "s2",
				status: "approved",
				frozen: { worked: 42.5, expected: 160, balanceEnd: -12.3, entries: 20, absenceDays: 1 },
			}),
		];
		renderSection("admin");

		expect(screen.getByText("Nadia")).toBeInTheDocument();
		expect(screen.getByText(/Backend/)).toBeInTheDocument();
		expect(
			screen.getByText("42.5 h worked · 160 h expected · balance −12.3 h at the close"),
		).toBeInTheDocument();
		expect(screen.getByRole("button", { name: /^Reopen/ })).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: /^Approve/ })).not.toBeInTheDocument();
	});

	it("marks an approved sheet whose contract has changed since, and keeps Reopen", () => {
		// Decision 23: the month is still approved and locked, the frozen
		// figures are still the record; the mark says the terms moved and
		// names the way back. A current approval carries no mark.
		state.sheets = [
			sheet({
				id: "s2",
				status: "approved",
				frozen: { worked: 42.5, expected: 160, balanceEnd: -12.3, entries: 20, absenceDays: 1 },
				supersededAt: "2026-10-20T10:00:00Z",
				supersededBy: "u-admin",
				supersededByName: "Omar",
				history: [
					{ at: "2026-10-01T09:00:00Z", by: "u1", action: "submitted" },
					{ at: "2026-10-02T09:00:00Z", by: "u-admin", action: "approved" },
					{ at: "2026-10-20T10:00:00Z", by: "u-admin", action: "terms_changed" },
				],
			}),
			sheet({
				id: "s3",
				month: "2026-08-01",
				status: "approved",
				frozen: { worked: 1, expected: 1, balanceEnd: 0, entries: 1, absenceDays: 0 },
			}),
		];
		renderSection("admin");

		expect(screen.getAllByText("Terms changed since")).toHaveLength(1);
		expect(screen.getByText(/The contract changed on Oct 20, 2026 by Omar/)).toBeInTheDocument();
		expect(screen.getByText(/reopen it to approve against the current terms/)).toBeInTheDocument();
		expect(screen.getAllByRole("button", { name: /^Reopen/ })).toHaveLength(2);
	});

	it("renders Approve and Ask for changes on a submitted sheet", () => {
		state.sheets = [sheet({ status: "submitted" })];
		renderSection("admin");

		expect(screen.getByText("Submitted")).toBeInTheDocument();
		expect(screen.getByText("Waiting on you")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: /^Approve/ })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: /^Ask for changes/ })).toBeInTheDocument();
	});

	it("names a member the API could not, rather than showing their id", () => {
		state.sheets = [sheet({ memberName: undefined, projectName: undefined })];
		renderSection("admin");

		expect(screen.getByText("A former member")).toBeInTheDocument();
		expect(screen.queryByText("u1")).not.toBeInTheDocument();
	});

	it("shows a viewer the sheet with no actions", () => {
		state.sheets = [sheet({ status: "submitted" })];
		renderSection("viewer");

		expect(screen.getByText("Submitted")).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: /^Approve/ })).not.toBeInTheDocument();
	});
});
