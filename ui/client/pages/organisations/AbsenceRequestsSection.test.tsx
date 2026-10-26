/**
 * A pending day off shows who, where, when, and the note — addressed to
 * the decider, never to the record — and the two ways to answer it. The
 * names are the row's own, which is what lets a manager read it: the
 * organisation's project list is an admin's.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AbsenceRequestsSection } from "./AbsenceRequestsSection";

const { idle } = vi.hoisted(() => ({
	idle: () => ({ isPending: false, mutate: vi.fn(), mutateAsync: vi.fn() }),
}));

vi.mock("@/entities/organisation", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/organisation")>("@/entities/organisation");
	return {
		...actual,
		useAbsenceRequests: () => ({
			data: [
				{
					id: "r1",
					projectId: "p1",
					projectName: "Backend",
					userId: "u1",
					memberName: "Nadia",
					date: "2026-11-03",
					type: "vacation",
					halfDay: true,
					note: "Dentist in the morning",
					status: "pending",
					requestedAt: "2026-10-20T09:00:00Z",
				},
			],
			error: null,
		}),
		// Neither list is read any more: a decider may not have them.
		useMembers: () => {
			throw new Error("the members are not read here");
		},
		useOrgProjects: () => {
			throw new Error("the projects are not read here");
		},
		useDecideAbsenceRequest: idle,
	};
});

afterEach(cleanup);

describe("AbsenceRequestsSection", () => {
	it("shows a pending request's note and offers Approve and Decline", () => {
		render(
			<QueryClientProvider client={new QueryClient()}>
				<AbsenceRequestsSection organisationId="o1" />
			</QueryClientProvider>,
		);

		expect(screen.getByText("Nadia")).toBeInTheDocument();
		expect(screen.getByText(/Backend/)).toBeInTheDocument();
		expect(screen.getByText(/half day/)).toBeInTheDocument();
		expect(screen.getByText(/Dentist in the morning/)).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "Decline" })).toBeInTheDocument();
	});
});
