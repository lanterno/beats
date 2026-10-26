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
	it("shows the caller's own months out of everyone's", () => {
		state.sheets = [
			sheet("s1", "u-me", "2026-09-01"),
			sheet("s2", "u-other", "2026-08-01"),
			sheet("s3", "u-me", "2026-07-01"),
		];
		render(
			<QueryClientProvider client={new QueryClient()}>
				<MyTimesheetsSection organisationId="o1" userId="u-me" />
			</QueryClientProvider>,
		);

		expect(screen.getByText("September 2026")).toBeInTheDocument();
		expect(screen.getByText("July 2026")).toBeInTheDocument();
		expect(screen.queryByText("August 2026")).not.toBeInTheDocument();
	});
});
