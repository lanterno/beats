/**
 * A team is a name and who is in it — the names resolved from the member
 * list — and "New team" opens the dialog that makes one.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TeamsSection } from "./TeamsSection";

const { idle } = vi.hoisted(() => ({
	idle: () => ({ isPending: false, mutate: vi.fn(), mutateAsync: vi.fn() }),
}));

vi.mock("@/entities/organisation", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/organisation")>("@/entities/organisation");
	return {
		...actual,
		useTeams: () => ({
			data: [{ id: "t1", name: "Platform", memberIds: ["u1", "u2"] }],
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
				{
					userId: "u2",
					name: "Omar",
					email: "o@example.com",
					role: "manager",
					joinedAt: "2026-01-01T00:00:00Z",
				},
			],
			error: null,
		}),
		useSaveTeam: idle,
		useDeleteTeam: idle,
	};
});

afterEach(cleanup);

describe("TeamsSection", () => {
	it("renders a team with its members' names", () => {
		render(
			<QueryClientProvider client={new QueryClient()}>
				<TeamsSection organisationId="o1" />
			</QueryClientProvider>,
		);

		expect(screen.getByText("Platform")).toBeInTheDocument();
		expect(screen.getByText("Nadia")).toBeInTheDocument();
		expect(screen.getByText("Omar")).toBeInTheDocument();
	});

	it("opens the team dialog from New team", () => {
		render(
			<QueryClientProvider client={new QueryClient()}>
				<TeamsSection organisationId="o1" />
			</QueryClientProvider>,
		);

		fireEvent.click(screen.getByRole("button", { name: /New team/ }));
		expect(screen.getByRole("dialog", { name: "New team" })).toBeInTheDocument();
	});
});
