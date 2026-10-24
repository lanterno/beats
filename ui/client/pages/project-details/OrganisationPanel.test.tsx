/**
 * The rail's Organisation panel by what the project is: an organisation's
 * project names its owner and links to what they see; a personal one offers
 * to connect only while the member belongs to an organisation, and never
 * when it is billed to a client, which the API would refuse.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Membership, Timesheet } from "@/entities/organisation";
import type { ProjectWithDuration } from "@/entities/project";
import { OrganisationPanel } from "./OrganisationPanel";

const { hooks } = vi.hoisted(() => ({
	hooks: {
		memberships: vi.fn<() => Membership[]>(() => []),
		timesheets: vi.fn<() => Timesheet[]>(() => []),
		submit: vi.fn(),
	},
}));

vi.mock("@/entities/organisation", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/organisation")>("@/entities/organisation");
	return {
		...actual,
		useMemberships: () => ({ data: hooks.memberships() }),
		useTimesheets: () => ({ data: hooks.timesheets() }),
		useSubmitTimesheet: () => ({ mutate: hooks.submit, isPending: false }),
	};
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
	beforeEach(() => {
		hooks.memberships.mockReturnValue([]);
		hooks.timesheets.mockReturnValue([]);
		hooks.submit.mockReset();
	});
	afterEach(cleanup);

	it("names the owner of an organisation's project and links to what they see", () => {
		renderPanel({
			...PERSONAL,
			organisation: {
				id: "o1",
				name: "Acme",
				sharedFrom: "2026-03-03T23:00:00Z",
				contractManaged: false,
			},
		});
		const panel = screen.getByRole("region", { name: "Organisation" });
		expect(panel).toHaveTextContent(/Acme owns this project/);
		expect(screen.getByRole("link", { name: "What Acme can see" })).toHaveAttribute(
			"href",
			"/organisations/o1/visible",
		);
	});

	it("lists my timesheets with what approval froze, and offers only unsettled ended months", () => {
		const sheet = (overrides: Partial<Timesheet>): Timesheet => ({
			id: "t",
			projectId: "p1",
			userId: "u1",
			month: "2026-08-01",
			status: "submitted",
			submittedAt: "2026-09-01T08:00:00Z",
			history: [],
			...overrides,
		});
		hooks.timesheets.mockReturnValue([
			sheet({
				id: "t-aug",
				month: "2026-08-01",
				status: "approved",
				frozen: { worked: 42.5, expected: 44, balanceEnd: -1.5, entries: 61, absenceDays: 2 },
			}),
			sheet({ id: "t-sep", month: "2026-09-01", status: "submitted" }),
			// Another project's sheet stays out of this panel.
			sheet({ id: "t-other", projectId: "p2", month: "2026-07-01" }),
		]);
		renderPanel({
			...PERSONAL,
			organisation: {
				id: "o1",
				name: "Acme",
				sharedFrom: "2026-03-03T23:00:00Z",
				contractManaged: true,
			},
		});
		const panel = screen.getByRole("region", { name: "Organisation" });

		expect(panel).toHaveTextContent("August 2026 — approved · 42.5 h");
		expect(panel).toHaveTextContent("September 2026 — submitted");
		expect(panel).toHaveTextContent(
			"Approval freezes the month and locks its days; a decider can reopen it.",
		);

		// Submitted and approved months are not offered again; open ended months are.
		const options = within(screen.getByRole("combobox", { name: "Month to submit" }))
			.getAllByRole("option")
			.map((o) => o.textContent);
		expect(options).not.toContain("September 2026");
		expect(options).not.toContain("August 2026");
		expect(options).toContain("July 2026");
		expect(options).not.toContain("October 2026");
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
