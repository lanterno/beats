/**
 * A pending day off shows who, where, when, and the note — addressed to
 * the decider, never to the record — and the two ways to answer it.
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
					userId: "u1",
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
		useMembers: () => ({
			data: [
				{
					userId: "u1",
					name: "Nadia",
					email: "n@example.com",
					role: "member",
					joinedAt: "2026-01-01T00:00:00Z",
				},
			],
			error: null,
		}),
		useOrgProjects: () => ({
			data: [{ id: "p1", name: "Backend", archived: false, kind: "day_job", members: [] }],
			error: null,
		}),
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
