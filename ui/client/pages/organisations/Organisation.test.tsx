/**
 * What the organisation page shows for which role, tab by tab: every member
 * gets the plain account of what the organisation can see and the way out;
 * the members, invites and projects are an admin's. And when the API answers
 * 404 — the membership ended, or never was — the page points at the
 * archive rather than at nothing.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
		useAssignMembers: idle,
		useUnassignMember: idle,
		useCreateOrgProject: idle,
		useUpdateOrgProject: idle,
		useTeams: list,
		useAbsenceRequests: list,
		useTimesheets: list,
		useAuditLog: list,
		useManagedContract: list,
		useSaveTeam: idle,
		useDeleteTeam: idle,
		useDecideAbsenceRequest: idle,
		useDecideTimesheet: idle,
		useReopenTimesheet: idle,
		useSubmitTimesheet: idle,
		useSetManagedContract: idle,
		useEnterTime: idle,
	};
});
vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return { ...actual, useProjects: list };
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

/** Switch to the tab named `name` in the organisation tablist. */
function openTab(name: string) {
	fireEvent.click(screen.getByRole("tab", { name }));
}

describe("Organisation", () => {
	it("as a member, has one tab: what Acme can see, your timesheets, and the way out", () => {
		state.membership = { data: membership("member"), error: null };
		renderPage();

		expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Timesheets"]);
		expect(screen.getByRole("heading", { name: "What Acme can see" })).toBeInTheDocument();
		expect(screen.getByRole("link", { name: "See the actual data" })).toHaveAttribute(
			"href",
			"/organisations/o1/visible",
		);
		expect(screen.getByRole("button", { name: "Leave Acme" })).toBeInTheDocument();
		expect(screen.queryByRole("heading", { name: "Members" })).not.toBeInTheDocument();
		expect(screen.queryByRole("heading", { name: "Absence requests" })).not.toBeInTheDocument();
		expect(screen.queryByRole("heading", { name: "Timesheets" })).not.toBeInTheDocument();
		expect(screen.queryByRole("heading", { name: "Audit log" })).not.toBeInTheDocument();
		expect(screen.getByRole("heading", { name: "Your timesheets" })).toBeInTheDocument();
		expect(screen.queryByRole("link", { name: "This month's record" })).not.toBeInTheDocument();
		// The archive used to be reachable only from the index, or from the
		// 404; it is a control in the page bar now.
		expect(screen.getByRole("link", { name: "Your hours in this organisation" })).toHaveAttribute(
			"href",
			"/organisations/o1/archive",
		);
	});

	it("as a manager, lands on the approvals but has no admin tabs", () => {
		state.membership = { data: membership("manager"), error: null };
		renderPage();

		expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
			"Approvals",
			"Timesheets",
		]);
		expect(screen.getByRole("heading", { name: "Absence requests" })).toBeInTheDocument();
		expect(screen.getByRole("heading", { name: "Timesheets" })).toBeInTheDocument();
		expect(screen.queryByRole("heading", { name: "Members" })).not.toBeInTheDocument();
		expect(screen.queryByRole("heading", { name: /Teams/ })).not.toBeInTheDocument();
		expect(screen.queryByRole("heading", { name: "Audit log" })).not.toBeInTheDocument();
	});

	it("as an owner, has every tab, each with its sections", () => {
		state.membership = { data: membership("owner"), error: null };
		renderPage();

		expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
			"People",
			"Projects",
			"Approvals",
			"Timesheets",
			"Audit",
			"Settings",
		]);

		expect(screen.getByRole("heading", { name: "Members" })).toBeInTheDocument();
		expect(screen.getByRole("heading", { name: /Teams/ })).toBeInTheDocument();
		expect(screen.getByRole("heading", { name: /Invites/ })).toBeInTheDocument();

		openTab("Projects");
		expect(screen.getByRole("heading", { name: /Projects/ })).toBeInTheDocument();

		openTab("Approvals");
		expect(screen.getByRole("heading", { name: "Absence requests" })).toBeInTheDocument();
		expect(screen.getByRole("heading", { name: "Timesheets" })).toBeInTheDocument();

		openTab("Timesheets");
		expect(screen.getByRole("heading", { name: "Your timesheets" })).toBeInTheDocument();
		expect(screen.getByRole("heading", { name: "What Acme can see" })).toBeInTheDocument();
		// An admin leaves from Settings, not here.
		expect(screen.queryByRole("button", { name: "Leave Acme" })).not.toBeInTheDocument();

		openTab("Audit");
		expect(screen.getByRole("heading", { name: "Audit log" })).toBeInTheDocument();

		openTab("Settings");
		expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "Leave Acme" })).toBeInTheDocument();

		expect(screen.getByRole("link", { name: "This month's record" })).toHaveAttribute(
			"href",
			"/organisations/o1/record",
		);
	});

	it("an unknown ?tab= falls back to the first tab the role can see", () => {
		state.membership = { data: membership("owner"), error: null };
		render(
			<QueryClientProvider client={new QueryClient()}>
				<MemoryRouter initialEntries={["/organisations/o1?tab=nonsense"]}>
					<Routes>
						<Route path="/organisations/:id" element={<Organisation />} />
					</Routes>
				</MemoryRouter>
			</QueryClientProvider>,
		);

		expect(screen.getByRole("tab", { name: "People" })).toHaveAttribute("aria-selected", "true");
		expect(screen.getByRole("heading", { name: "Members" })).toBeInTheDocument();
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
