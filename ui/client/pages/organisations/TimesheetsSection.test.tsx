/**
 * An approved sheet shows what approval froze and the way to reopen it;
 * a submitted one waits on Approve or Ask for changes. A viewer reads the
 * same list with no buttons. The names come off the row — a manager and a
 * viewer are shown this list and may not read the organisation's projects.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
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
			<TimesheetsSection organisationId="o1" role={role} />
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
		expect(screen.getByRole("button", { name: "Reopen…" })).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
	});

	it("renders Approve and Ask for changes on a submitted sheet", () => {
		state.sheets = [sheet({ status: "submitted" })];
		renderSection("admin");

		expect(screen.getByText("Submitted")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "Ask for changes" })).toBeInTheDocument();
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
		expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
	});
});
