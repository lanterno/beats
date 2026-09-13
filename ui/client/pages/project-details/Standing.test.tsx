/**
 * The standing's states (docs/project-page-roadmap.md, "The page" and
 * "States"): the balance's tone and proof, the first-week rule, the side
 * project's average, a day job without a contract, the missing-region
 * notice, a past week open, the quiet-project alert. The arithmetic is the
 * entity's (standing.test.ts); this pins what the panel says with it.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
	Contract,
	ContractDay,
	ContractWeek,
	Ledger,
	LedgerWeek,
	ProjectWithDuration,
} from "@/entities/project";
import { Standing, type StandingProps } from "./Standing";

const health = vi.fn();
const dismiss = vi.fn();
vi.mock("@/entities/intelligence", () => ({
	useProjectHealth: () => health(),
	useDismissInboxItem: () => ({ mutate: dismiss, isPending: false }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// The mockup: Thu Sep 10, 2026; 80 % of 42 h since Aug 3 after 60 % from Jan 5.
const TODAY = "2026-09-10";
const CONTRACT: Contract = {
	terms: [
		{ effectiveFrom: "2026-01-05", scheduleType: "part_time", fullTimeHours: 42, percentage: 0.6 },
		{ effectiveFrom: "2026-08-03", scheduleType: "part_time", fullTimeHours: 42, percentage: 0.8 },
	],
	holidayCountry: "CH",
	holidaySubdivision: "ZH",
	openingBalanceHours: 2,
};

const BASE: ProjectWithDuration = {
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
};

const PER_DAY = 6.72;

function days(patches: Record<number, Partial<ContractDay>> = {}): ContractDay[] {
	return [0, 1, 2, 3, 4, 5, 6].map((i) => ({
		date: `2026-09-${String(7 + i).padStart(2, "0")}`,
		expected: i < 5 ? PER_DAY : 0,
		worked: 0,
		...patches[i],
	}));
}

// Friday booked off: 26.88 expected, 25.0 worked, 1.88 to go, +10.5 h as of today.
const WEEK: ContractWeek = {
	weekOf: "2026-09-07",
	expected: 26.88,
	worked: 25,
	remaining: 1.88,
	balance: 10.5,
	balanceAsOf: TODAY,
	balanceOpening: 2,
	balanceWorked: 848.5,
	balanceExpectedThrough: 840,
	days: days({
		0: { worked: 7.1 },
		1: { worked: 6.9 },
		2: { worked: 7.6 },
		3: { worked: 3.4 },
		4: { expected: 0, absence: { type: "vacation", halfDay: false } },
	}),
};

function ledgerWeek(weekOf: string, worked: number, goal: number | null = 8): LedgerWeek {
	return {
		weekOf,
		worked,
		days: [worked, 0, 0, 0, 0, 0, 0],
		effectiveGoal: goal,
		effectiveGoalType: "target",
		effectiveGoalOverridden: false,
		contractExpected: null,
		balanceEnd: null,
		notes: [],
	};
}

function renderStanding(overrides: Partial<StandingProps> = {}) {
	const props: StandingProps = {
		project: BASE,
		todayIso: TODAY,
		openWeekOf: "2026-09-07",
		currentWeek: WEEK,
		openWeek: WEEK,
		ledger: undefined,
		running: false,
		onBookTimeOff: vi.fn(),
		onEditGoal: vi.fn(),
		onAddContract: vi.fn(),
		onSetRegion: vi.fn(),
		...overrides,
	};
	render(<Standing {...props} />);
	return props;
}

/** The figure beside a label in the week's list. */
function figure(label: string): string | undefined {
	return screen.getByText(label).nextElementSibling?.textContent ?? undefined;
}

beforeEach(() => {
	health.mockReturnValue({ data: [] });
	dismiss.mockReset();
});
afterEach(cleanup);

describe("Standing on a day job", () => {
	it("says the balance in leaf with its proof, the projection and the week's figures", () => {
		renderStanding();

		const region = screen.getByRole("region", { name: "Where you stand" });
		const big = within(region).getByText("+10.5 h");
		expect(big).toHaveAttribute("data-tone", "over");
		expect(big).toHaveTextContent("over");
		expect(region).toHaveTextContent("+2.0 h brought forward");
		expect(region).toHaveTextContent("+848.5 h worked since Mon Jan 5");
		expect(region).toHaveTextContent("−840.0 h expected through Wed");
		expect(region).toHaveTextContent("By Sunday: +5.7 h if the week is met");
		expect(region).toHaveTextContent("+3.8 h if you stop now.");

		expect(region).toHaveTextContent("This week");
		expect(figure("Expected")).toBe("26.9 h");
		expect(figure("Worked")).toBe("25.0 h");
		expect(figure("Remaining")).toBe("1.9 h");
		expect(region).toHaveTextContent("33.6 h nominal − Fri vacation 6.7 h");
		expect(region).toHaveTextContent("1.9 h to go, all today. Friday is off.");
		expect(within(region).getByRole("button", { name: "Book time off" })).toBeInTheDocument();
		expect(within(region).queryByRole("button", { name: "Edit goal" })).not.toBeInTheDocument();
	});

	it("says an owed balance in persimmon, muted with its line in the contract's first week", () => {
		const owed = { ...WEEK, balance: -22.7 };
		renderStanding({ currentWeek: owed, openWeek: owed });
		expect(screen.getByText("−22.7 h")).toHaveAttribute("data-tone", "owed");
		expect(screen.queryByText(/First week under the contract/)).not.toBeInTheDocument();
		cleanup();

		const fresh: ProjectWithDuration = {
			...BASE,
			contract: {
				...CONTRACT,
				terms: [
					{
						effectiveFrom: "2026-09-07",
						scheduleType: "full_time",
						fullTimeHours: 42,
						percentage: 1,
					},
				],
			},
		};
		renderStanding({ project: fresh, currentWeek: owed, openWeek: owed });
		expect(screen.getByText("−22.7 h")).toHaveAttribute("data-tone", "muted");
		expect(screen.getByText(/First week under the contract/)).toBeInTheDocument();
		expect(screen.queryByText(/By Sunday/)).not.toBeInTheDocument();
	});

	it("offers to add a contract when there is none, and no balance", () => {
		const props = renderStanding({
			project: { ...BASE, contract: undefined },
			currentWeek: undefined,
			openWeek: undefined,
		});
		expect(screen.getByText(/No contract yet\./)).toBeInTheDocument();
		expect(screen.queryByText(/brought forward/)).not.toBeInTheDocument();
		screen.getByRole("button", { name: "Add contract" }).click();
		expect(props.onAddContract).toHaveBeenCalled();
	});

	it("carries the missing-region caveat under the proof, linking to the drawer", async () => {
		const props = renderStanding({
			project: { ...BASE, contract: { ...CONTRACT, holidayCountry: undefined } },
		});
		expect(screen.getByText(/Public holidays are not deducted/)).toBeInTheDocument();
		await userEvent.click(screen.getByRole("button", { name: "set the holiday region" }));
		expect(props.onSetRegion).toHaveBeenCalled();
	});

	it("keeps the balance pinned to today on a past week and says how that week closed", () => {
		const past: ContractWeek = {
			weekOf: "2026-08-31",
			expected: 33.6,
			worked: 32.9,
			remaining: 0.7,
			balance: 10.5,
			balanceAsOf: TODAY,
			balanceOpening: 2,
			balanceWorked: 848.5,
			balanceExpectedThrough: 840,
			days: [],
		};
		renderStanding({ openWeekOf: "2026-08-31", openWeek: past });
		const region = screen.getByRole("region", { name: "Where you stand" });
		expect(region).toHaveTextContent("as of Thu Sep 10");
		expect(region).toHaveTextContent("Week 36 · closed 0.7 h short");
		expect(region).not.toHaveTextContent("to go");
	});

	it("gives a week still to come its figures and no verdict", () => {
		const next: ContractWeek = {
			...WEEK,
			weekOf: "2026-09-14",
			expected: 33.6,
			worked: 0,
			remaining: 33.6,
			days: [],
		};
		renderStanding({ openWeekOf: "2026-09-14", openWeek: next });
		const region = screen.getByRole("region", { name: "Where you stand" });
		expect(region).toHaveTextContent("Week 38");
		expect(figure("Remaining")).toBe("33.6 h");
		expect(region).not.toHaveTextContent("closed");
		expect(region).not.toHaveTextContent("to go");
	});

	it("says how a contract's first week closed by the balance's move, not the hours logged before it", () => {
		// Starts Wed Sep 2 at 0: 4 h on the Monday before it, 24 h Wed–Fri against 25.2 h.
		const project: ProjectWithDuration = {
			...BASE,
			contract: {
				...CONTRACT,
				terms: [
					{
						effectiveFrom: "2026-09-02",
						scheduleType: "full_time",
						fullTimeHours: 42,
						percentage: 1,
					},
				],
				openingBalanceHours: 0,
			},
		};
		const startWeek: ContractWeek = {
			...WEEK,
			weekOf: "2026-08-31",
			expected: 25.2,
			worked: 28,
			remaining: -2.8,
			days: [],
		};
		const ledger: Ledger = {
			since: "2026-09-02",
			totals: { expected: 50.4, worked: 38, balance: -12.4 },
			weeks: [
				{ ...ledgerWeek("2026-09-07", 10, 42), contractExpected: 42, balanceEnd: null },
				{ ...ledgerWeek("2026-08-31", 28, 42), contractExpected: 25.2, balanceEnd: -1.2 },
				{ ...ledgerWeek("2026-08-24", 0, null) },
			],
		};
		renderStanding({ project, openWeekOf: "2026-08-31", openWeek: startWeek, ledger });
		expect(screen.getByRole("region", { name: "Where you stand" })).toHaveTextContent(
			"Week 36 · closed 1.2 h short",
		);
	});

	it("waits for the week on a day job rather than standing the personal goal in", () => {
		const withGoal = { ...BASE, weeklyGoal: 40, effectiveGoal: 40 };
		renderStanding({ project: withGoal, currentWeek: undefined, openWeek: undefined });
		const region = screen.getByRole("region", { name: "Where you stand" });
		expect(figure("Worked")).toBe("…");
		expect(within(region).queryByText("Goal")).not.toBeInTheDocument();
		expect(within(region).queryByRole("alert")).not.toBeInTheDocument();
		cleanup();

		const failure = new Error("Unknown holiday region: CH / XX");
		renderStanding({
			project: withGoal,
			currentWeek: undefined,
			openWeek: undefined,
			currentWeekError: failure,
			openWeekError: failure,
		});
		const failed = screen.getByRole("region", { name: "Where you stand" });
		const alerts = within(failed).getAllByRole("alert");
		expect(alerts).toHaveLength(2);
		for (const alert of alerts) expect(alert).toHaveTextContent("Unknown holiday region: CH / XX");
		expect(within(failed).queryByText("Goal")).not.toBeInTheDocument();
		expect(failed).not.toHaveTextContent("…");
	});

	it("shows the quiet-project alert with its Snooze", async () => {
		health.mockReturnValue({
			data: [{ project_id: "p1", project_name: "Contract Co", alert: "stale_project" }],
		});
		renderStanding();
		expect(screen.getByText("This project has been quiet for a while.")).toBeInTheDocument();
		await userEvent.click(screen.getByRole("button", { name: /Snooze 7d/ }));
		expect(dismiss).toHaveBeenCalledWith("project_health:p1", expect.anything());
	});
});

describe("Standing on a side project", () => {
	const loom: ProjectWithDuration = {
		...BASE,
		name: "Loom",
		kind: "side_project",
		contract: undefined,
		weeklyGoal: 8,
		goalType: "target",
	};
	const ledger: Ledger = {
		since: null,
		totals: null,
		weeks: [
			ledgerWeek("2026-09-07", 4.8),
			ledgerWeek("2026-08-31", 8.4),
			ledgerWeek("2026-08-24", 5.9),
			ledgerWeek("2026-08-17", 9),
			ledgerWeek("2026-08-10", 4),
			ledgerWeek("2026-08-03", 7.5),
		],
	};

	it("shows the four-week average and the week against the goal", () => {
		const props = renderStanding({
			project: loom,
			currentWeek: undefined,
			openWeek: undefined,
			ledger,
		});
		const region = screen.getByRole("region", { name: "Where you stand" });
		expect(region).toHaveTextContent("4-week average");
		expect(region).toHaveTextContent("6.8 h / week");
		expect(region).toHaveTextContent("Goal met 2 of the last 4 weeks");
		expect(region).toHaveTextContent("No contract on a side project");
		expect(figure("Goal")).toBe("8 h");
		expect(figure("Worked")).toBe("4.8 h");
		expect(figure("Remaining")).toBe("3.2 h");
		expect(region).toHaveTextContent("3.2 h to go over Thu – Sun — about 50 min a day.");
		expect(screen.queryByText("Expected")).not.toBeInTheDocument();
		screen.getByRole("button", { name: "Edit goal" }).click();
		expect(props.onEditGoal).toHaveBeenCalled();
	});

	it("claims nothing about closed weeks while the ledger loads, and says why it failed", () => {
		renderStanding({
			project: loom,
			currentWeek: undefined,
			openWeek: undefined,
			ledgerLoading: true,
		});
		expect(screen.getByRole("region", { name: "Where you stand" })).not.toHaveTextContent(
			"No weeks closed yet",
		);
		cleanup();

		renderStanding({
			project: loom,
			currentWeek: undefined,
			openWeek: undefined,
			ledgerError: new Error("The API did not answer"),
		});
		const region = screen.getByRole("region", { name: "Where you stand" });
		expect(within(region).getByRole("alert")).toHaveTextContent("The API did not answer");
		expect(region).not.toHaveTextContent("No weeks closed yet");
	});
});
