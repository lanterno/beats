/**
 * The settings drawer's PUT body for the work-contract fields, and its foot.
 * The API reads `kind` and `contract` by presence — a stale contract sent
 * with another kind is a 409, and one left out with a kind change is what
 * clears it — so what the drawer omits matters as much as what it sends,
 * and a kind change says so before save. Archive asks first and then leaves
 * the page; an archived project restores. On an organisation's project the
 * organisation's fields are locked and sent as they came, and the foot names
 * the owner instead of offering Archive; a personal project offers to connect
 * once the member belongs to an organisation.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Membership } from "@/entities/organisation";
import type { Contract, Project } from "@/entities/project";
import { ProjectSettingsDrawer } from "./ProjectSettingsDrawer";

const { hooks } = vi.hoisted(() => ({
	hooks: {
		update: vi.fn(),
		archive: vi.fn(),
		unarchive: vi.fn(),
		navigate: vi.fn(),
		memberships: vi.fn<() => Membership[]>(() => []),
	},
}));

vi.mock("@/entities/organisation", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/organisation")>("@/entities/organisation");
	return { ...actual, useMemberships: () => ({ data: hooks.memberships() }) };
});

vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return {
		...actual,
		useUpdateProject: () => ({ mutate: hooks.update, isPending: false }),
		useArchiveProject: () => ({ mutate: hooks.archive, isPending: false }),
		useUnarchiveProject: () => ({ mutate: hooks.unarchive, isPending: false }),
		useProjects: () => ({ data: [] }),
		useHolidayRegions: () => ({
			data: [
				{ code: "CH", name: "Switzerland", subdivisions: [{ code: "ZH", name: "Zürich" }] },
				{ code: "FR", name: "France", subdivisions: [] },
			],
		}),
	};
});
// What a region change reads, at the network: France has Bastille Day, and
// a contract with no region has no holidays at all.
vi.mock("@/entities/project/api/projectApi", async (importOriginal) => ({
	...(await importOriginal<typeof import("@/entities/project/api/projectApi")>()),
	fetchRegionHolidays: vi.fn(async (country: string) => {
		if (country !== "FR") throw new Error(`no calendar for ${country}`);
		return [
			{ date: "2026-07-14", name: "National Day" },
			{ date: "2026-12-25", name: "Christmas Day" },
		];
	}),
}));
vi.mock("@/entities/github", () => ({
	useGitHubStatus: () => ({ data: { connected: false } }),
}));
vi.mock("react-router", async () => {
	const actual = await vi.importActual<typeof import("react-router")>("react-router");
	return { ...actual, useNavigate: () => hooks.navigate };
});
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const CONTRACT: Contract = {
	terms: [
		{ effectiveFrom: "2026-01-05", scheduleType: "full_time", fullTimeHours: 40, percentage: 1 },
		{
			effectiveFrom: "2026-04-01",
			scheduleType: "part_time",
			fullTimeHours: 40,
			percentage: 0.8,
		},
	],
	openingBalanceHours: 2,
	companyHolidays: [],
	holidaysNotGiven: [],
};

const DAY_JOB: Project = {
	id: "p1",
	name: "Employer",
	color: "#888",
	archived: false,
	goalOverrides: [],
	autostartRepos: [],
	kind: "day_job",
	contract: CONTRACT,
};

const KIND_LINE = /Changing the kind deletes the contract/;

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

describe("ProjectSettingsDrawer", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		hooks.memberships.mockReturnValue([]);
	});
	afterEach(cleanup);

	it("leaves `contract` out of the PUT when the kind leaves day_job, and says so before save", async () => {
		render(<ProjectSettingsDrawer project={DAY_JOB} open onClose={vi.fn()} />);
		expect(screen.queryByText(KIND_LINE)).not.toBeInTheDocument();

		await userEvent.click(screen.getByRole("radio", { name: /Freelance/ }));
		expect(screen.getByText(KIND_LINE)).toBeInTheDocument();
		await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

		expect(hooks.update).toHaveBeenCalledTimes(1);
		const body = hooks.update.mock.calls[0][0];
		expect(body.kind).toBe("freelance");
		expect(body).not.toHaveProperty("contract");
	});

	it("carries the terms through unchanged and sends the frame the form edited", async () => {
		render(<ProjectSettingsDrawer project={DAY_JOB} open onClose={vi.fn()} />);

		await userEvent.selectOptions(screen.getByLabelText("Holiday region"), "CH");
		await userEvent.selectOptions(screen.getByLabelText(/Region within Switzerland/), "ZH");
		await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

		const body = hooks.update.mock.calls[0][0];
		expect(body.kind).toBe("day_job");
		// The mapper's exact null-filling is mappers.test's business; here it
		// is the composition: both terms as they were, the frame as edited.
		expect(body.contract).toMatchObject({
			terms: [
				{ effective_from: "2026-01-05", schedule_type: "full_time", percentage: 1 },
				{ effective_from: "2026-04-01", schedule_type: "part_time", percentage: 0.8 },
			],
			holiday_country: "CH",
			holiday_subdivision: "ZH",
			opening_balance_hours: 2,
		});
		expect(body.contract.terms).toHaveLength(2);
	});

	it("drops the marks a region change would make working days, and only those, when asked", async () => {
		// Left over from a region with no Bastille Day; the March date matches nothing in France.
		const marked: Project = {
			...DAY_JOB,
			contract: { ...CONTRACT, holidaysNotGiven: ["2026-03-04", "2026-07-14"] },
		};
		render(
			<QueryClientProvider client={new QueryClient()}>
				<ProjectSettingsDrawer project={marked} open onClose={vi.fn()} />
			</QueryClientProvider>,
		);

		await userEvent.selectOptions(screen.getByLabelText("Holiday region"), "FR");
		expect(await screen.findByText(/National Day/)).toBeInTheDocument();
		await userEvent.click(screen.getByRole("button", { name: "Clear the mark" }));
		await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

		const body = hooks.update.mock.calls[0][0];
		expect(body.contract.holiday_country).toBe("FR");
		expect(body.contract.holidays_not_given).toEqual(["2026-03-04"]);
	});

	it("saves a day job that has no contract yet without demanding one", async () => {
		const waiting: Project = { ...DAY_JOB, contract: undefined };
		render(<ProjectSettingsDrawer project={waiting} open onClose={vi.fn()} />);

		const name = screen.getByLabelText("Name");
		await userEvent.clear(name);
		await userEvent.type(name, "Employer AG");
		// Nothing to lose by a kind change here, so nothing is said.
		await userEvent.click(screen.getByRole("radio", { name: /Freelance/ }));
		expect(screen.queryByText(KIND_LINE)).not.toBeInTheDocument();
		await userEvent.click(screen.getByRole("radio", { name: /Day job/ }));
		await userEvent.click(screen.getByRole("checkbox", { name: /Set up the contract now/ }));
		await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

		expect(hooks.update).toHaveBeenCalledTimes(1);
		const body = hooks.update.mock.calls[0][0];
		expect(body).toMatchObject({ name: "Employer AG", kind: "day_job" });
		// Left out, not null: null would clear a contract, absence keeps what is stored.
		expect(body).not.toHaveProperty("contract");
	});

	it("creates the first term when a project without a contract becomes a day job", async () => {
		const sideProject: Project = { ...DAY_JOB, kind: "side_project", contract: undefined };
		render(<ProjectSettingsDrawer project={sideProject} open onClose={vi.fn()} />);

		await userEvent.click(screen.getByRole("radio", { name: /Day job/ }));
		await userEvent.click(screen.getByRole("radio", { name: /Custom/ }));
		await userEvent.type(screen.getByLabelText("Hours per week"), "32");
		await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

		const body = hooks.update.mock.calls[0][0];
		expect(body.kind).toBe("day_job");
		expect(body.contract.terms).toHaveLength(1);
		expect(body.contract.terms[0]).toMatchObject({
			schedule_type: "custom",
			weekly_hours: 32,
			full_time_hours: null,
			percentage: null,
		});
	});

	it("archives only after a confirm, then closes and leaves for the dashboard", async () => {
		const onClose = vi.fn();
		render(<ProjectSettingsDrawer project={DAY_JOB} open onClose={onClose} />);
		expect(
			screen.getByText(/Archiving hides Employer from pickers, lists, and the sidebar/),
		).toBeInTheDocument();

		const foot = screen.getByRole("region", { name: "Archive" });
		await userEvent.click(within(foot).getByRole("button", { name: "Archive project" }));
		expect(hooks.archive).not.toHaveBeenCalled();
		await userEvent.click(within(foot).getByRole("button", { name: "Cancel" }));
		await userEvent.click(within(foot).getByRole("button", { name: "Archive project" }));
		await userEvent.click(within(foot).getByRole("button", { name: "Archive project" }));

		expect(hooks.archive).toHaveBeenCalledTimes(1);
		expect(hooks.archive).toHaveBeenCalledWith("p1", expect.anything());
		hooks.archive.mock.calls[0][1].onSuccess();
		expect(onClose).toHaveBeenCalled();
		expect(hooks.navigate).toHaveBeenCalledWith("/app");
	});

	it("restores an archived project instead", async () => {
		render(
			<ProjectSettingsDrawer project={{ ...DAY_JOB, archived: true }} open onClose={vi.fn()} />,
		);

		expect(screen.queryByRole("button", { name: "Archive project" })).not.toBeInTheDocument();
		await userEvent.click(screen.getByRole("button", { name: "Restore project" }));
		expect(hooks.unarchive).toHaveBeenCalledWith("p1", expect.anything());
	});

	it("locks the organisation's fields on its project, sends them as they came, and names the owner instead of Archive", async () => {
		const owned: Project = {
			...DAY_JOB,
			organisation: { id: "o1", name: "Acme", sharedFrom: "2026-03-04T00:00:00Z" },
		};
		render(
			<MemoryRouter>
				<ProjectSettingsDrawer project={owned} open onClose={vi.fn()} />
			</MemoryRouter>,
		);

		expect(screen.getByLabelText("Name")).toBeDisabled();
		expect(screen.getByRole("radio", { name: /Freelance/ })).toBeDisabled();
		expect(screen.getByText(/Acme owns this project's name, colour, kind/)).toBeInTheDocument();
		// The goal and the contract's frame stay the member's.
		expect(screen.getByLabelText("Holiday region")).toBeEnabled();

		expect(screen.queryByRole("region", { name: "Archive" })).not.toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "Archive project" })).not.toBeInTheDocument();
		const foot = screen.getByRole("region", { name: "Organisation" });
		expect(foot).toHaveTextContent(/Acme owns this project\. Leaving the organisation/);
		expect(within(foot).getByRole("link", { name: "Open Acme" })).toHaveAttribute(
			"href",
			"/organisations/o1",
		);

		await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
		const body = hooks.update.mock.calls[0][0];
		expect(body).toMatchObject({ name: "Employer", color: "#888", kind: "day_job" });
	});

	it("offers to connect a personal project once the member belongs to an organisation", () => {
		hooks.memberships.mockReturnValue([ACME]);
		render(
			<MemoryRouter>
				<ProjectSettingsDrawer project={DAY_JOB} open onClose={vi.fn()} />
			</MemoryRouter>,
		);

		expect(screen.getByRole("region", { name: "Archive" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "Connect to an organisation…" })).toBeInTheDocument();
	});

	it("offers no connect without an active membership", () => {
		hooks.memberships.mockReturnValue([
			{ ...ACME, leftAt: "2026-09-30T00:00:00Z", leftReason: "left" },
		]);
		render(<ProjectSettingsDrawer project={DAY_JOB} open onClose={vi.fn()} />);

		expect(
			screen.queryByRole("button", { name: "Connect to an organisation…" }),
		).not.toBeInTheDocument();
		expect(screen.queryByRole("region", { name: "Organisation" })).not.toBeInTheDocument();
	});
});
