/**
 * The settings drawer's PUT body for the work-contract fields. The API
 * reads `kind` and `contract` by presence — a stale contract sent with
 * another kind is a 409, and one left out with a kind change is what
 * clears it — so what the drawer omits matters as much as what it sends.
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Project } from "@/entities/project";
import { ProjectSettingsDrawer } from "./ProjectSettingsDrawer";

const mutate = vi.fn();

vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return {
		...actual,
		useUpdateProject: () => ({ mutate, isPending: false }),
		// The override panel the drawer hosts reaches for this one.
		useUpdateGoalOverrides: () => ({ mutate: vi.fn(), isPending: false }),
		useProjects: () => ({ data: [] }),
		useHolidayRegions: () => ({
			data: [
				{ code: "CH", name: "Switzerland", subdivisions: [{ code: "ZH", name: "Zürich" }] },
				{ code: "FR", name: "France", subdivisions: [] },
			],
		}),
	};
});
vi.mock("@/entities/github", () => ({
	useGitHubStatus: () => ({ data: { connected: false } }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const DAY_JOB: Project = {
	id: "p1",
	name: "Employer",
	color: "#888",
	archived: false,
	goalOverrides: [],
	autostartRepos: [],
	kind: "day_job",
	contract: {
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
	},
};

describe("ProjectSettingsDrawer", () => {
	beforeEach(() => mutate.mockReset());
	afterEach(cleanup);

	it("leaves `contract` out of the PUT when the kind leaves day_job", async () => {
		render(<ProjectSettingsDrawer project={DAY_JOB} open onClose={vi.fn()} />);

		await userEvent.click(screen.getByRole("radio", { name: /Freelance/ }));
		await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

		expect(mutate).toHaveBeenCalledTimes(1);
		const body = mutate.mock.calls[0][0];
		expect(body.kind).toBe("freelance");
		expect(body).not.toHaveProperty("contract");
	});

	it("carries the terms through unchanged and sends the frame the form edited", async () => {
		render(<ProjectSettingsDrawer project={DAY_JOB} open onClose={vi.fn()} />);

		await userEvent.selectOptions(screen.getByLabelText("Holiday region"), "CH");
		await userEvent.selectOptions(screen.getByLabelText(/Region within Switzerland/), "ZH");
		await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

		const body = mutate.mock.calls[0][0];
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

	it("saves a day job that has no contract yet without demanding one", async () => {
		const waiting: Project = { ...DAY_JOB, contract: undefined };
		render(<ProjectSettingsDrawer project={waiting} open onClose={vi.fn()} />);

		const name = screen.getByLabelText("Name");
		await userEvent.clear(name);
		await userEvent.type(name, "Employer AG");
		await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

		expect(mutate).toHaveBeenCalledTimes(1);
		const body = mutate.mock.calls[0][0];
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

		const body = mutate.mock.calls[0][0];
		expect(body.kind).toBe("day_job");
		expect(body.contract.terms).toHaveLength(1);
		expect(body.contract.terms[0]).toMatchObject({
			schedule_type: "custom",
			weekly_hours: 32,
			full_time_hours: null,
			percentage: null,
		});
	});
});
