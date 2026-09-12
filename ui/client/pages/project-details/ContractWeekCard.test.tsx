import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Contract, ContractWeek } from "@/entities/project";
import { ContractWeekCard } from "./ContractWeekCard";
import { getMondayIsoFor } from "./weekIso";

const useContractWeekMock = vi.fn();

vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return {
		...actual,
		useContractWeek: (projectId: string, weekOf?: string) => useContractWeekMock(projectId, weekOf),
	};
});

// Terms dated long ago, so "which term is in force this week" never depends
// on when the suite runs.
const FULL_TIME: Contract = {
	terms: [
		{ effectiveFrom: "2000-01-03", scheduleType: "full_time", fullTimeHours: 40, percentage: 1 },
	],
	openingBalanceHours: 0,
};
const OBJECTIVE: Contract = {
	terms: [{ effectiveFrom: "2000-01-03", scheduleType: "objective" }],
	openingBalanceHours: 0,
};
const ZERO_HOURS: Contract = {
	terms: [{ effectiveFrom: "2000-01-03", scheduleType: "custom", weeklyHours: 0 }],
	openingBalanceHours: 0,
};

const DATES = [
	"2026-04-06",
	"2026-04-07",
	"2026-04-08",
	"2026-04-09",
	"2026-04-10",
	"2026-04-11",
	"2026-04-12",
];

function week(overrides: Partial<ContractWeek>): ContractWeek {
	return {
		weekOf: "2026-04-06",
		expected: 40,
		worked: 0,
		remaining: 40,
		balance: 0,
		days: DATES.map((date, i) => ({ date, expected: i < 5 ? 8 : 0, worked: 0 })),
		...overrides,
	};
}

function loaded(data: ContractWeek) {
	return { data, isLoading: false, error: null };
}

/** The value beside a headline label: the <dd> after its <dt>. */
function stat(label: string): string | undefined {
	return screen.getByText(label).nextElementSibling?.textContent ?? undefined;
}

describe("ContractWeekCard", () => {
	beforeEach(() => useContractWeekMock.mockReset());
	afterEach(cleanup);

	it("says an overtime balance in words, with the week's figures and its days", () => {
		const days = week({}).days;
		days[2] = {
			...days[2],
			expected: 4,
			worked: 3.5,
			absence: { type: "vacation", halfDay: true },
		};
		days[4] = { ...days[4], expected: 0, holiday: "Good Friday" };
		useContractWeekMock.mockReturnValue(
			loaded(week({ expected: 28, worked: 24.5, remaining: 3.5, balance: 4.5, days })),
		);

		render(<ContractWeekCard projectId="p1" contract={FULL_TIME} personalGoal={null} />);

		expect(stat("Expected")).toBe("28.0 h");
		expect(stat("Worked")).toBe("24.5 h");
		expect(stat("Remaining")).toBe("3.5 h");
		expect(screen.getByText("+4.5 h over")).toBeInTheDocument();

		const cells = within(screen.getByRole("list", { name: "Weekdays" })).getAllByRole("listitem");
		expect(cells).toHaveLength(5);
		expect(cells[2]).toHaveTextContent("Vacation ½");
		expect(cells[2]).toHaveTextContent("3.5 h");
		expect(cells[4]).toHaveTextContent("Good Friday");
	});

	it("says an owed balance, and a week already past its expectation as over", () => {
		useContractWeekMock.mockReturnValue(
			loaded(week({ expected: 32, worked: 33.5, remaining: -1.5, balance: -2 })),
		);

		render(<ContractWeekCard projectId="p1" contract={FULL_TIME} personalGoal={null} />);

		expect(screen.getByText("−2.0 h owed")).toBeInTheDocument();
		expect(stat("Over this week")).toBe("1.5 h");
		expect(screen.queryByText("Remaining")).not.toBeInTheDocument();
	});

	it("calls what rounds to nothing even or 0.0 h, never a signed zero", () => {
		const days = week({}).days;
		days[5] = { ...days[5], worked: 0.03 }; // two minutes on Saturday
		useContractWeekMock.mockReturnValue(
			loaded(week({ worked: 40.04, remaining: -0.04, balance: -0.04, days })),
		);

		render(<ContractWeekCard projectId="p1" contract={FULL_TIME} personalGoal={null} />);

		expect(screen.getByText("even")).toBeInTheDocument();
		expect(screen.queryByText(/owed|over/i)).not.toBeInTheDocument();
		expect(stat("Remaining")).toBe("0.0 h");
		expect(screen.queryByText(/at the weekend/)).not.toBeInTheDocument();
	});

	it("keeps today's balance under a week the contract does not govern", () => {
		// The API's balance is as of today, whichever week is asked for: an
		// objective week still shows what today's term has built up.
		useContractWeekMock.mockReturnValue(
			loaded(week({ expected: undefined, remaining: undefined, worked: 3, balance: 5 })),
		);

		render(<ContractWeekCard projectId="p1" contract={OBJECTIVE} personalGoal={null} />);

		expect(screen.getByText(/objective-based term/)).toBeInTheDocument();
		expect(screen.getByText("+5.0 h over")).toBeInTheDocument();
	});

	it("shows an objective week as hours worked against the personal goal, with no expectation or balance", () => {
		useContractWeekMock.mockReturnValue(
			loaded(week({ expected: undefined, remaining: undefined, balance: undefined, worked: 12 })),
		);

		render(<ContractWeekCard projectId="p1" contract={OBJECTIVE} personalGoal={20} />);

		expect(stat("Worked")).toBe("12.0 h");
		expect(stat("Personal goal")).toBe("20.0 h");
		expect(screen.queryByText("Expected")).not.toBeInTheDocument();
		expect(screen.queryByText(/Balance/)).not.toBeInTheDocument();
		expect(screen.getByText(/objective-based term/)).toBeInTheDocument();
	});

	it("says a term of 0 hours expects nothing, in its own words", () => {
		// The API answers the same nulls as for an objective term; the term on
		// the week's Monday is what tells the two apart.
		useContractWeekMock.mockReturnValue(
			loaded(week({ expected: undefined, remaining: undefined, balance: undefined, worked: 2 })),
		);

		render(<ContractWeekCard projectId="p1" contract={ZERO_HOURS} personalGoal={null} />);

		expect(stat("Worked")).toBe("2.0 h");
		expect(screen.getByText("A term of 0 hours: no weekly expectation.")).toBeInTheDocument();
		expect(screen.queryByText(/objective-based term/)).not.toBeInTheDocument();
		expect(screen.queryByText("Expected")).not.toBeInTheDocument();
	});

	it("asks for the previous week's Monday when stepping back, and keeps the balance as of today", async () => {
		useContractWeekMock.mockReturnValue(loaded(week({ worked: 10, remaining: 30, balance: 1 })));

		render(<ContractWeekCard projectId="p1" contract={FULL_TIME} personalGoal={null} />);
		expect(useContractWeekMock).toHaveBeenLastCalledWith("p1", getMondayIsoFor(0));

		await userEvent.click(screen.getByRole("button", { name: "Previous week" }));

		expect(useContractWeekMock).toHaveBeenLastCalledWith("p1", getMondayIsoFor(1));
		expect(screen.getByText("Last week")).toBeInTheDocument();
		expect(screen.getByText(/Balance as of today/)).toBeInTheDocument();
	});

	it("reports a failed load in place", () => {
		useContractWeekMock.mockReturnValue({
			data: undefined,
			isLoading: false,
			error: new Error("x"),
		});

		render(<ContractWeekCard projectId="p1" contract={FULL_TIME} personalGoal={null} />);

		expect(screen.getByRole("alert")).toBeInTheDocument();
		expect(screen.queryByText("Expected")).not.toBeInTheDocument();
	});
});
