/**
 * The index page's states that depend on what the account holds: an
 * invitation waiting is offered with Accept, and an organisation left is
 * named as left, with its archive the way back to one's own hours.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Invitation, Membership } from "@/entities/organisation";
import Organisations from "./Organisations";

const { state, idle } = vi.hoisted(() => ({
	state: {
		invitations: [] as unknown[],
		memberships: [] as unknown[],
	},
	idle: () => ({ isPending: false, mutate: vi.fn(), mutateAsync: vi.fn() }),
}));

vi.mock("@/entities/organisation", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/organisation")>("@/entities/organisation");
	return {
		...actual,
		useInvitations: () => ({ data: state.invitations, error: null, isLoading: false }),
		useMemberships: () => ({ data: state.memberships, error: null, isLoading: false }),
		useJoinOrganisation: idle,
		useCreateOrganisation: idle,
	};
});

const ACME: Membership = {
	organisation: {
		id: "o1",
		name: "Acme",
		weekStart: "monday",
		timezone: "Europe/Berlin",
		createdAt: "2026-01-05T09:00:00Z",
	},
	role: "member",
	joinedAt: "2026-01-05T09:00:00Z",
	leftAt: "2026-09-30T16:00:00Z",
	leftReason: "left",
};

const KITE: Membership = {
	organisation: {
		id: "o2",
		name: "Kite Studio",
		weekStart: "monday",
		timezone: "Europe/Berlin",
		createdAt: "2026-03-01T09:00:00Z",
	},
	role: "owner",
	joinedAt: "2026-03-01T09:00:00Z",
};

const INVITATION: Invitation = {
	token: "tok-1",
	role: "admin",
	expiresAt: "2026-11-07T12:00:00Z",
	organisation: { id: "o3", name: "Beacon" },
};

function renderPage() {
	render(
		<QueryClientProvider client={new QueryClient()}>
			<MemoryRouter initialEntries={["/organisations"]}>
				<Organisations />
			</MemoryRouter>
		</QueryClientProvider>,
	);
}

afterEach(cleanup);

describe("Organisations", () => {
	it("offers a waiting invitation with Accept, and names an organisation left", () => {
		state.invitations = [INVITATION];
		state.memberships = [KITE, ACME];
		renderPage();

		const invitations = screen.getByRole("region", { name: "Invitations" });
		expect(invitations).toHaveTextContent("Beacon");
		expect(within(invitations).getByRole("button", { name: "Accept" })).toBeInTheDocument();

		expect(screen.getByRole("link", { name: "Kite Studio" })).toHaveAttribute(
			"href",
			"/organisations/o2",
		);
		expect(screen.getByRole("link", { name: "Acme (left)" })).toHaveAttribute(
			"href",
			"/organisations/o1/archive",
		);
	});

	it("with nothing yet, says what an organisation is for", () => {
		state.invitations = [];
		state.memberships = [];
		renderPage();

		expect(screen.queryByRole("region", { name: "Invitations" })).not.toBeInTheDocument();
		expect(
			screen.getByText("An organisation owns projects and reads the hours on them."),
		).toBeInTheDocument();
	});
});
