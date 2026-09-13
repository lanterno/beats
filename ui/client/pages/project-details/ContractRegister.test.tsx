/**
 * The register: the term in force and the next one read off the terms, the
 * state after `ended_on`, the term list's add / edit / remove as
 * whole-contract PUTs (the last term is never removable, no two start on one
 * day), the goal overrides a day job still stores, the missing-region state
 * and a day job without a contract, and the Goal variant's next goal and its
 * overrides with their identity-based remove.
 * The chart's geometry is stepChart.test's.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Contract, ContractTerm, ProjectWithDuration } from "@/entities/project";
import { ContractRegister } from "./ContractRegister";

const updateContract = vi.fn();
const updateOverrides = vi.fn();

vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return {
		...actual,
		useUpdateContract: () => ({ mutate: updateContract, isPending: false }),
		useUpdateGoalOverrides: () => ({ mutate: updateOverrides, isPending: false }),
		useHolidayRegions: () => ({
			data: [{ code: "CH", name: "Switzerland", subdivisions: [{ code: "ZH", name: "Zürich" }] }],
		}),
	};
});
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// The mockup's register, on Thu Sep 10, 2026.
const TODAY = "2026-09-10";
const SIXTY: ContractTerm = {
	effectiveFrom: "2026-01-05",
	scheduleType: "part_time",
	fullTimeHours: 42,
	percentage: 0.6,
};
const EIGHTY: ContractTerm = {
	effectiveFrom: "2026-08-03",
	scheduleType: "part_time",
	fullTimeHours: 42,
	percentage: 0.8,
	note: "Four days a week from August",
};
const FULL: ContractTerm = {
	effectiveFrom: "2027-01-04",
	scheduleType: "full_time",
	fullTimeHours: 42,
	percentage: 1,
};
const LATER: ContractTerm = {
	effectiveFrom: "2027-07-05",
	scheduleType: "part_time",
	fullTimeHours: 42,
	percentage: 0.6,
};
const CONTRACT: Contract = {
	terms: [SIXTY, EIGHTY, FULL],
	holidayCountry: "CH",
	holidaySubdivision: "ZH",
	openingBalanceHours: 2,
};

function project(extra: Partial<ProjectWithDuration>): ProjectWithDuration {
	return {
		id: "p1",
		name: "Contract Co",
		color: "#5B9CF6",
		archived: false,
		goalOverrides: [],
		autostartRepos: [],
		kind: "day_job",
		contract: CONTRACT,
		totalMinutes: 0,
		weeklyMinutes: 0,
		...extra,
	};
}

function renderRegister(p: ProjectWithDuration, firstTrackedIso?: string) {
	const onOpenSettings = vi.fn();
	render(
		<ContractRegister
			project={p}
			todayIso={TODAY}
			firstTrackedIso={firstTrackedIso}
			onOpenSettings={onOpenSettings}
		/>,
	);
	return onOpenSettings;
}

const sentTerms = () =>
	updateContract.mock.calls[0][0].contract.terms as { effective_from: string }[];

beforeEach(() => {
	updateContract.mockReset();
	updateOverrides.mockReset();
});
afterEach(cleanup);

describe("ContractRegister on a day job", () => {
	it("names the term in force and the next, marks each term, and states the constants", () => {
		// Two changes planned: Next is the nearer, not the last.
		renderRegister(project({ contract: { ...CONTRACT, terms: [SIXTY, EIGHTY, FULL, LATER] } }));
		const region = screen.getByRole("region", { name: "Contract" });

		expect(region).toHaveTextContent("Part time · 80% of 42 h");
		expect(region).toHaveTextContent("33.6 h/week · since Mon Aug 3, 2026");
		expect(region).toHaveTextContent("Next → Full time · 42 h/week from Mon Jan 4, 2027");
		expect(within(region).getByRole("img", { name: /Hours per week/ })).toBeInTheDocument();

		const rows = within(screen.getByRole("list", { name: "Terms" })).getAllByRole("listitem");
		expect(rows).toHaveLength(4);
		expect(rows[0]).not.toHaveTextContent(/In force|Planned/);
		expect(rows[1]).toHaveTextContent("In force");
		expect(rows[1]).toHaveTextContent("“Four days a week from August”");
		expect(rows[2]).toHaveTextContent("Planned");
		expect(rows[3]).toHaveTextContent("Planned");

		expect(region).toHaveTextContent(
			"Holidays Switzerland · Zürich · Brought forward +2.0 h · Ended —",
		);
	});

	it("after ended_on keeps the last term's headline, with nothing in force or to come", () => {
		renderRegister(
			project({ contract: { ...CONTRACT, terms: [SIXTY, EIGHTY], endedOn: "2026-08-31" } }),
		);
		const region = screen.getByRole("region", { name: "Contract" });

		expect(region).toHaveTextContent("Part time · 80% of 42 h");
		expect(region).not.toHaveTextContent(/In force|Planned|Next →/);
		expect(region).toHaveTextContent("Ended Aug 31, 2026");
	});

	it("adds a term from “Change contract from…” and PUTs the whole contract in date order", async () => {
		renderRegister(project({ contract: { ...CONTRACT, terms: [SIXTY, EIGHTY] } }));

		await userEvent.click(screen.getByRole("button", { name: /Change contract from/ }));
		const dialog = screen.getByRole("dialog");
		fireEvent.change(within(dialog).getByLabelText("From"), { target: { value: "2026-03-02" } });
		await userEvent.click(within(dialog).getByRole("radio", { name: /Custom/ }));
		await userEvent.type(within(dialog).getByLabelText("Hours per week"), "20");
		await userEvent.click(within(dialog).getByRole("button", { name: "Save term" }));

		expect(updateContract).toHaveBeenCalledTimes(1);
		const { projectId, contract } = updateContract.mock.calls[0][0];
		expect(projectId).toBe("p1");
		// The frame rides along untouched; the new term lands between the two.
		expect(contract.holiday_country).toBe("CH");
		expect(contract.opening_balance_hours).toBe(2);
		expect(sentTerms().map((t) => t.effective_from)).toEqual([
			"2026-01-05",
			"2026-03-02",
			"2026-08-03",
		]);
		expect(contract.terms[1]).toMatchObject({ schedule_type: "custom", weekly_hours: 20 });
	});

	it("edits one term in place and keeps the others", async () => {
		renderRegister(project({}));

		await userEvent.click(screen.getByRole("button", { name: "Edit term from Aug 3, 2026" }));
		const dialog = screen.getByRole("dialog");
		const percentage = within(dialog).getByLabelText("Percentage");
		await userEvent.clear(percentage);
		await userEvent.type(percentage, "90");
		await userEvent.click(within(dialog).getByRole("button", { name: "Save term" }));

		const terms = updateContract.mock.calls[0][0].contract.terms;
		expect(terms.map((t: { percentage: number }) => t.percentage)).toEqual([0.6, 0.9, 1]);
		expect(terms[1]).toMatchObject({
			effective_from: "2026-08-03",
			note: "Four days a week from August",
		});
	});

	it("removes a term but never the last one", async () => {
		renderRegister(project({}));
		await userEvent.click(screen.getByRole("button", { name: "Remove term from Jan 5, 2026" }));
		expect(sentTerms().map((t) => t.effective_from)).toEqual(["2026-08-03", "2027-01-04"]);
		cleanup();

		renderRegister(project({ contract: { ...CONTRACT, terms: [EIGHTY] } }));
		expect(screen.getByRole("button", { name: /Remove term/ })).toBeDisabled();
	});

	it("refuses a new term on a day another term starts, before sending anything", async () => {
		renderRegister(project({}));

		await userEvent.click(screen.getByRole("button", { name: /Change contract from/ }));
		const dialog = screen.getByRole("dialog");
		fireEvent.change(within(dialog).getByLabelText("From"), { target: { value: "2026-08-03" } });
		await userEvent.click(within(dialog).getByRole("button", { name: "Save term" }));

		expect(updateContract).not.toHaveBeenCalled();
		expect(within(dialog).getByLabelText("From")).toHaveAttribute("aria-invalid", "true");
	});

	it("lists the goal overrides a day job with a contract still stores, and removes one", async () => {
		renderRegister(
			project({
				goalOverrides: [
					{ weekOf: "2026-07-27", weeklyGoal: 30, goalType: "target" },
					{ weekOf: "2026-08-10", weeklyGoal: null },
				],
			}),
		);
		const region = screen.getByRole("region", { name: "Contract" });
		const list = within(region).getByRole("list", { name: "Goal overrides" });

		await userEvent.click(
			within(list).getByRole("button", { name: "Remove override for Jul 27, 2026" }),
		);

		expect(updateOverrides).toHaveBeenCalledTimes(1);
		expect(updateOverrides.mock.calls[0][0].overrides).toEqual([
			{
				week_of: "2026-08-10",
				effective_from: null,
				weekly_goal: null,
				goal_type: null,
				note: null,
			},
		]);
	});

	it("says public holidays are not deducted until a region is set, and offers to set it", async () => {
		const onOpenSettings = renderRegister(
			project({
				contract: { ...CONTRACT, holidayCountry: undefined, holidaySubdivision: undefined },
			}),
		);
		const region = screen.getByRole("region", { name: "Contract" });
		expect(region).toHaveTextContent("Public holidays are not deducted.");
		expect(region).not.toHaveTextContent("Holidays Switzerland");

		await userEvent.click(within(region).getByRole("button", { name: "Set region" }));
		expect(onOpenSettings).toHaveBeenCalledWith("holidayCountry");
	});

	it("offers to add a contract on a day job without one", async () => {
		const onOpenSettings = renderRegister(project({ contract: undefined }));
		const region = screen.getByRole("region", { name: "Contract" });
		// The sentence is the standing's; the rail only names the state.
		expect(region).toHaveTextContent("No contract yet");
		expect(region).not.toHaveTextContent("keeps a balance");
		await userEvent.click(within(region).getByRole("button", { name: "Add contract" }));
		expect(onOpenSettings).toHaveBeenCalledWith("scheduleType");
	});
});

describe("ContractRegister's Goal variant", () => {
	it("states the goal since the override that set it, the next one, its history and the overrides", () => {
		renderRegister(
			project({
				kind: "side_project",
				contract: undefined,
				weeklyGoal: 5,
				goalType: "target",
				goalOverrides: [
					{ effectiveFrom: "2026-07-06", weeklyGoal: 8, goalType: "target" },
					{ weekOf: "2026-07-27", weeklyGoal: null },
					{ effectiveFrom: "2027-02-01", weeklyGoal: 12, goalType: "target" },
					{ effectiveFrom: "2026-11-02", weeklyGoal: 10, goalType: "target" },
				],
			}),
			"2026-03-02",
		);
		const region = screen.getByRole("region", { name: "Goal" });

		expect(region).toHaveTextContent("8 h / week · target");
		expect(region).toHaveTextContent("since Mon Jul 6, 2026");
		expect(region).toHaveTextContent("Next → 10 h / week · target from Mon Nov 2, 2026");
		expect(
			within(region).getByRole("img", { name: /5 h from Mar 2, 2026; 8 h from Jul 6, 2026/ }),
		).toBeInTheDocument();
		const rows = within(screen.getByRole("list", { name: "Goal overrides" })).getAllByRole(
			"listitem",
		);
		expect(rows[0]).toHaveTextContent("In force");
		expect(rows[1]).toHaveTextContent("No goal that week");
		expect(screen.queryByRole("region", { name: "Contract" })).not.toBeInTheDocument();
	});

	it("removes the clicked override alone when two share a week", async () => {
		// Two overrides stored for one Monday (legacy data): filtering by the
		// week would take both.
		renderRegister(
			project({
				kind: "side_project",
				contract: undefined,
				weeklyGoal: 5,
				goalOverrides: [
					{ effectiveFrom: "2026-07-06", weeklyGoal: 8, goalType: "target" },
					{ weekOf: "2026-07-27", weeklyGoal: null },
					{ weekOf: "2026-07-27", weeklyGoal: 4, goalType: "cap" },
				],
			}),
		);

		const removes = screen.getAllByRole("button", { name: "Remove override for Jul 27, 2026" });
		expect(removes).toHaveLength(2);
		await userEvent.click(removes[1]);

		expect(updateOverrides).toHaveBeenCalledTimes(1);
		const { projectId, overrides } = updateOverrides.mock.calls[0][0];
		expect(projectId).toBe("p1");
		expect(overrides.map((o: { weekly_goal: number | null }) => o.weekly_goal)).toEqual([8, null]);
	});
});
