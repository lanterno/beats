/**
 * The rail's Organisation panel by what the project is: an organisation's
 * project names its owner and links to what they see; a personal one offers
 * to connect only while the member belongs to an organisation, and never
 * when it is billed to a client, which the API would refuse.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Membership } from "@/entities/organisation";
import type { ProjectWithDuration } from "@/entities/project";
import { OrganisationPanel } from "./OrganisationPanel";

const { hooks } = vi.hoisted(() => ({
	hooks: { memberships: vi.fn<() => Membership[]>(() => []) },
}));

vi.mock("@/entities/organisation", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/organisation")>("@/entities/organisation");
	return { ...actual, useMemberships: () => ({ data: hooks.memberships() }) };
});

const ACME: Membership = {
	organisation: {
		id: "o1",
		name: "Acme",
		weekStart: "monday",
		timezone: "Europe/Zurich",
		createdAt: "2026-01-01T00:00:00Z",
	},
	role: "member",
	joinedAt: "2026-03-04T00:00:00Z",
};

const PERSONAL: ProjectWithDuration = {
	id: "p1",
	name: "Garden",
	color: "#888",
	archived: false,
	goalOverrides: [],
	autostartRepos: [],
	kind: "side_project",
	totalMinutes: 0,
	weeklyMinutes: 0,
	effectiveGoalOverridden: false,
};

function renderPanel(project: ProjectWithDuration, billed = false) {
	render(
		<MemoryRouter>
			<OrganisationPanel project={project} todayIso="2026-10-24" billed={billed} />
		</MemoryRouter>,
	);
}

describe("OrganisationPanel", () => {
	beforeEach(() => hooks.memberships.mockReturnValue([]));
	afterEach(cleanup);

	it("names the owner of an organisation's project and links to what they see", () => {
		renderPanel({
			...PERSONAL,
			organisation: { id: "o1", name: "Acme", sharedFrom: "2026-03-03T23:00:00Z" },
		});
		const panel = screen.getByRole("region", { name: "Organisation" });
		expect(panel).toHaveTextContent(/Acme owns this project/);
		expect(screen.getByRole("link", { name: "What Acme can see" })).toHaveAttribute(
			"href",
			"/organisations/o1/visible",
		);
	});

	it("offers to connect a personal project once the member belongs to an organisation", () => {
		hooks.memberships.mockReturnValue([ACME]);
		renderPanel(PERSONAL);
		expect(screen.getByRole("button", { name: "Connect to Acme…" })).toBeInTheDocument();
	});

	it("offers nothing without an active membership, or on a billed project", () => {
		hooks.memberships.mockReturnValue([
			{ ...ACME, leftAt: "2026-09-30T00:00:00Z", leftReason: "left" },
		]);
		renderPanel(PERSONAL);
		expect(screen.queryByRole("region", { name: "Organisation" })).not.toBeInTheDocument();

		cleanup();
		hooks.memberships.mockReturnValue([ACME]);
		renderPanel(PERSONAL, true);
		expect(screen.queryByRole("region", { name: "Organisation" })).not.toBeInTheDocument();
	});
});
