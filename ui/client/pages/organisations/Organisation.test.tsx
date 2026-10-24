/**
 * What the organisation page shows for which role: every member gets the
 * plain account of what the organisation can see and the way out; the
 * members, invites and projects are an admin's. And when the API answers
 * 404 — the membership ended, or never was — the page points at the
 * archive rather than at nothing.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Membership, OrgRole } from "@/entities/organisation";
import { ApiError } from "@/shared/api";
import Organisation from "./Organisation";

const { state, idle, list } = vi.hoisted(() => ({
	state: {
		membership: { data: undefined, error: null } as { data?: unknown; error: unknown },
	},
	idle: () => ({ isPending: false, mutate: vi.fn(), mutateAsync: vi.fn() }),
	list: () => ({ data: [], error: null }),
}));

vi.mock("@/entities/organisation", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/organisation")>("@/entities/organisation");
	return {
		...actual,
		useMembership: () => state.membership,
		useMembers: list,
		useInvites: list,
		useJoinRequests: list,
		useOrgProjects: list,
		useLeaveOrganisation: idle,
		useUpdateOrganisation: idle,
		useSetMemberRole: idle,
		useRemoveMember: idle,
		useCreateInvite: idle,
		useRevokeInvite: idle,
		useDecideJoinRequest: idle,
		useAssignMember: idle,
		useUnassignMember: idle,
		useCreateOrgProject: idle,
		useUpdateOrgProject: idle,
	};
});
vi.mock("@/features/auth", () => ({
	useAuth: () => ({
		isAuthenticated: true,
		isLoading: false,
		token: "t",
		user: { email: "me@example.com", displayName: "Me" },
	}),
}));

function membership(role: OrgRole): Membership {
	return {
		organisation: {
			id: "o1",
			name: "Acme",
			weekStart: "monday",
			timezone: "Europe/Berlin",
			createdAt: "2026-01-05T09:00:00Z",
		},
		role,
		joinedAt: "2026-01-05T09:00:00Z",
	};
}

function renderPage() {
	render(
		<QueryClientProvider client={new QueryClient()}>
			<MemoryRouter initialEntries={["/organisations/o1"]}>
				<Routes>
					<Route path="/organisations/:id" element={<Organisation />} />
				</Routes>
			</MemoryRouter>
		</QueryClientProvider>,
	);
}

afterEach(cleanup);

describe("Organisation", () => {
	it("as a member, explains what Acme can see and offers to leave, and no admin section", () => {
		state.membership = { data: membership("member"), error: null };
		renderPage();

		expect(screen.getByRole("heading", { name: "What Acme can see" })).toBeInTheDocument();
		expect(screen.getByRole("link", { name: "See the actual data" })).toHaveAttribute(
			"href",
			"/organisations/o1/visible",
		);
		expect(screen.getByRole("button", { name: "Leave Acme" })).toBeInTheDocument();
		expect(screen.queryByRole("heading", { name: "Members" })).not.toBeInTheDocument();
		expect(screen.queryByRole("heading", { name: /Invites/ })).not.toBeInTheDocument();
		expect(screen.queryByRole("heading", { name: /Projects/ })).not.toBeInTheDocument();
		expect(screen.queryByRole("link", { name: "This month's record" })).not.toBeInTheDocument();
	});

	it("as an owner, shows the members, invites and projects", () => {
		state.membership = { data: membership("owner"), error: null };
		renderPage();

		expect(screen.getByRole("heading", { name: "Members" })).toBeInTheDocument();
		expect(screen.getByRole("heading", { name: /Invites/ })).toBeInTheDocument();
		expect(screen.getByRole("heading", { name: /Projects/ })).toBeInTheDocument();
		expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument();
		expect(screen.getByRole("link", { name: "This month's record" })).toHaveAttribute(
			"href",
			"/organisations/o1/record",
		);
		expect(screen.getByRole("button", { name: "Leave Acme" })).toBeInTheDocument();
	});

	it("when not a member, says so and points at the archive", () => {
		state.membership = { data: undefined, error: new ApiError(404, "Not a member") };
		renderPage();

		expect(screen.getByRole("alert")).toHaveTextContent(
			"You're not a member of this organisation.",
		);
		expect(screen.getByRole("link", { name: "Your hours" })).toHaveAttribute(
			"href",
			"/organisations/o1/archive",
		);
	});
});
