/**
 * "Your timesheets" is the caller's own months. A decider's read answers
 * with everyone's, so theirs are picked out by `userId` — the membership's
 * own id. It used to match the address on the member row, which an account
 * that changed its email, or came in through single sign-on, no longer has:
 * the section then showed a decider "No months submitted yet." over their
 * own submitted months.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Timesheet } from "@/entities/organisation";
import { MyTimesheetsSection } from "./MyTimesheetsSection";

const { state } = vi.hoisted(() => ({ state: { sheets: [] as unknown[] } }));

vi.mock("@/entities/organisation", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/organisation")>("@/entities/organisation");
	return {
		...actual,
		useTimesheets: () => ({ data: state.sheets, error: null }),
		useSubmitTimesheet: () => ({ isPending: false, mutate: vi.fn() }),
	};
});
vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return { ...actual, useProjects: () => ({ data: [], error: null }) };
});

function sheet(id: string, userId: string, month: string): Timesheet {
	return {
		id,
		projectId: "p1",
		projectName: "Backend",
		userId,
		month,
		status: "submitted",
		submittedAt: "2026-10-01T09:00:00Z",
		history: [],
	};
}

afterEach(cleanup);

describe("MyTimesheetsSection", () => {
	it("tells the member when the contract changed after a month was approved", () => {
		state.sheets = [
			{
				...sheet("s1", "u-me", "2026-09-01"),
				status: "approved",
				frozen: { worked: 42.5, expected: 160, balanceEnd: -12.3, entries: 20, absenceDays: 1 },
				supersededAt: "2026-10-20T10:00:00Z",
			},
		];
		render(
			<QueryClientProvider client={new QueryClient()}>
				<MyTimesheetsSection organisationId="o1" userId="u-me" timezone="Europe/Berlin" />
			</QueryClientProvider>,
		);

		expect(screen.getByText("Terms changed since")).toBeInTheDocument();
		expect(screen.getByText(/The contract changed on Oct 20, 2026, after/)).toBeInTheDocument();
		// Still an approved month, frozen figures and all: nothing to resubmit.
		expect(screen.getByText(/42.5 h worked/)).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: /^Resubmit/ })).not.toBeInTheDocument();
	});

	it("shows the caller's own months out of everyone's", () => {
		state.sheets = [
			sheet("s1", "u-me", "2026-09-01"),
			sheet("s2", "u-other", "2026-08-01"),
			sheet("s3", "u-me", "2026-07-01"),
		];
		render(
			<QueryClientProvider client={new QueryClient()}>
				<MyTimesheetsSection organisationId="o1" userId="u-me" timezone="Europe/Berlin" />
			</QueryClientProvider>,
		);

		expect(screen.getByText("September 2026")).toBeInTheDocument();
		expect(screen.getByText("July 2026")).toBeInTheDocument();
		expect(screen.queryByText("August 2026")).not.toBeInTheDocument();
	});
});
