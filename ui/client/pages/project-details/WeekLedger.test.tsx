/**
 * The ledger panel: rule and quiet rows among the weeks, the goal cell that
 * opens the override popover only where the contract does not govern, the
 * CSV, a week opened from its label, the count back to the opening balance
 * and the two foot lines, and the adjustment rows that open their dialog.
 * The row shapes are the entity's (ledger.test.ts).
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Ledger, LedgerWeek, ProjectWithDuration } from "@/entities/project";
import { WeekLedger, type WeekLedgerProps } from "./WeekLedger";

const overrides = vi.fn();
vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return {
		...actual,
		useUpdateGoalOverrides: () => ({ mutate: overrides, isPending: false }),
		useRecordAdjustment: () => ({ mutateAsync: vi.fn() }),
		useRemoveAdjustment: () => ({ mutateAsync: vi.fn() }),
	};
});
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const TODAY = "2026-09-10";

const DAY_JOB: ProjectWithDuration = {
	id: "p1",
	name: "Contract Co",
	color: "#5B9CF6",
	archived: false,
	goalOverrides: [],
	autostartRepos: [],
	kind: "day_job",
	contract: {
		terms: [
			{
				effectiveFrom: "2026-01-05",
				scheduleType: "part_time",
				fullTimeHours: 42,
				percentage: 0.6,
			},
			{
				effectiveFrom: "2026-08-03",
				scheduleType: "part_time",
				fullTimeHours: 42,
				percentage: 0.8,
				note: "Four days a week from August",
			},
		],
		holidayCountry: "CH",
		openingBalanceHours: 2,
		companyHolidays: [],
		holidaysNotGiven: [],
	},
	totalMinutes: 77_040,
	weeklyMinutes: 0,
};

function week(weekOf: string, patch: Partial<LedgerWeek> = {}): LedgerWeek {
	const row = {
		weekOf,
		worked: 33.6,
		days: [6.72, 6.72, 6.72, 6.72, 6.72, 0, 0],
		effectiveGoal: 33.6,
		effectiveGoalType: "target" as const,
		effectiveGoalOverridden: false,
		contractExpected: 33.6,
		balanceEnd: 5,
		notes: [],
		adjustments: [],
		...patch,
	};
	// The API's move on a full week of the contract, null exactly when the
	// close is; a week a contract starts or ends in sends its own.
	const moved =
		row.balanceEnd === null || row.contractExpected === null
			? null
			: Math.round((row.worked - row.contractExpected) * 100) / 100;
	return { balanceMoved: moved, ...row };
}

const LEDGER: Ledger = {
	since: "2026-01-05",
	totals: { expected: 840, worked: 848.5, adjusted: 0, balance: 10.5 },
	endedBalance: null,
	weeks: [
		week("2026-09-07", { balanceEnd: null }),
		week("2026-08-31", { worked: 32.9, days: [6.9, 6.4, 6.7, 6.5, 6.4, 0, 0], balanceEnd: 5.7 }),
		week("2026-08-03", { balanceEnd: 6.4 }),
		week("2026-07-27", {
			worked: 27.1,
			effectiveGoal: 25.2,
			contractExpected: 25.2,
			balanceEnd: 4.4,
			notes: [{ date: "2026-07-28", kind: "sick", halfDay: true }],
		}),
		week("2026-07-20", {
			worked: 0,
			days: [0, 0, 0, 0, 0, 0, 0],
			contractExpected: 0,
			balanceEnd: 2.5,
			notes: [{ date: "2026-07-20", kind: "vacation", halfDay: false }],
		}),
		week("2026-07-13", {
			worked: 0,
			days: [0, 0, 0, 0, 0, 0, 0],
			contractExpected: 0,
			balanceEnd: 2.5,
			notes: [{ date: "2026-07-13", kind: "vacation", halfDay: false }],
		}),
		week("2026-07-06", {
			worked: 24.1,
			effectiveGoal: 25.2,
			contractExpected: 25.2,
			balanceEnd: 2.5,
		}),
	],
};

function renderLedger(over: Partial<WeekLedgerProps> = {}) {
	const props: WeekLedgerProps = {
		project: DAY_JOB,
		todayIso: TODAY,
		ledger: LEDGER,
		weeks: 8,
		onShowMore: vi.fn(),
		onOpenWeek: vi.fn(),
		sessionCount: 412,
		...over,
	};
	render(<WeekLedger {...props} />);
	return props;
}

beforeEach(() => overrides.mockReset());
afterEach(cleanup);

describe("WeekLedger on a day job", () => {
	it("lays out the weeks newest first with a rule row and a quiet row, the current week left out", () => {
		renderLedger();
		const region = screen.getByRole("region", { name: "Earlier weeks" });
		const rows = within(region).getAllByRole("row").slice(1);
		expect(rows.map((r) => r.textContent?.slice(0, 12))).toEqual([
			expect.stringMatching(/^W36/),
			expect.stringMatching(/^W32/),
			expect.stringMatching(/^From Mon Aug/),
			expect.stringMatching(/^W31/),
			expect.stringMatching(/^·· 2 weeks/),
			expect.stringMatching(/^W28/),
		]);
		expect(region).not.toHaveTextContent("W37");

		const w36 = rows[0];
		expect(w36).toHaveTextContent("Aug 31 – Sep 6");
		expect(
			within(w36)
				.getAllByRole("cell")
				.map((c) => c.textContent),
		).toEqual(["W36Aug 31 – Sep 6", "", "33.6", "32.9", "−0.7", "+5.7"]);
		expect(rows[2]).toHaveTextContent(
			"From Mon Aug 3, 2026 · Part time 80% of 42 h = 33.6 h/wk was 60% · 25.2 h · “Four days a week from August”",
		);
		expect(rows[3]).toHaveTextContent("Tue Jul 28 · sick ½");
		expect(rows[4]).toHaveTextContent("·· 2 weeks away · Jul 13 – 26 · vacation ··");
		// A governed week's expectation is the contract's: no override to offer.
		expect(within(w36).getByText("33.6").closest("button")).toBeNull();
	});

	it("counts the weeks back to the opening balance and writes the two foot lines", async () => {
		const props = renderLedger();
		const region = screen.getByRole("region", { name: "Earlier weeks" });
		expect(region).toHaveTextContent("26 more back to the opening balance");
		await userEvent.click(screen.getByRole("button", { name: "Show 5 more weeks" }));
		expect(props.onShowMore).toHaveBeenCalled();
		expect(region).toHaveTextContent(
			"Since Mon Jan 5, 2026 · 840.0 h expected · 848.5 h worked · +8.5 h (+2.0 h brought forward)",
		);
		expect(region).toHaveTextContent("All time 1,284 h · 412 sessions");
	});

	it("copies the rows as CSV and opens a week from its label", async () => {
		const writeText = vi.fn(() => Promise.resolve());
		Object.assign(navigator, { clipboard: { writeText } });
		const props = renderLedger();

		await userEvent.click(screen.getByRole("button", { name: "Copy as CSV" }));
		expect(writeText).toHaveBeenCalledWith(
			expect.stringMatching(/^week,expected,worked,delta,balance\n2026-08-31,33.6,32.9,-0.7,5.7\n/),
		);

		await userEvent.click(screen.getByRole("button", { name: /^Open W31/ }));
		expect(props.onOpenWeek).toHaveBeenCalledWith("2026-07-27");
	});

	it("shows an adjustment under its week, counts it in the foot line, and opens it", async () => {
		const payout = {
			id: "a1",
			date: "2026-09-02",
			kind: "delta" as const,
			hours: -10,
			note: "August",
			applied: -10,
		};
		renderLedger({
			ledger: {
				...LEDGER,
				totals: { expected: 840, worked: 848.5, adjusted: -10, balance: 0.5 },
				weeks: LEDGER.weeks.map((w) =>
					w.weekOf === "2026-08-31" ? { ...w, adjustments: [payout] } : w,
				),
			},
		});
		const region = screen.getByRole("region", { name: "Earlier weeks" });
		const rows = within(region).getAllByRole("row").slice(1);
		expect(rows[0]).toHaveTextContent(/^W36/);
		// The pill, and its hours in the +/− column; the balance cell is blank.
		const [pill, ...figures] = within(rows[1]).getAllByRole("cell");
		expect(pill).toHaveTextContent("Wed Sep 2 · Adjusted −10.0 h “August”");
		expect(figures.map((c) => c.textContent)).toEqual(["−10.0", ""]);
		expect(region).toHaveTextContent("+8.5 h (+2.0 h brought forward, −10.0 h adjusted)");

		await userEvent.click(within(rows[1]).getByRole("button", { name: /^Change adjustment/ }));
		const dialog = screen.getByRole("dialog", { name: "Change adjustment" });
		expect(within(dialog).getByLabelText("Hours")).toHaveValue(10);
		expect(within(dialog).getByRole("button", { name: "Remove" })).toBeInTheDocument();
	});
});

describe("WeekLedger on a contract that started this week", () => {
	it("shows the opening rule and says there are no earlier weeks yet", async () => {
		const fresh: ProjectWithDuration = {
			...DAY_JOB,
			totalMinutes: 148,
			contract: {
				terms: [
					{
						effectiveFrom: "2026-09-07",
						scheduleType: "full_time",
						fullTimeHours: 42,
						percentage: 1,
					},
				],
				openingBalanceHours: 0,
				companyHolidays: [],
				holidaysNotGiven: [],
			},
		};
		renderLedger({
			project: fresh,
			sessionCount: 1,
			ledger: {
				since: "2026-09-07",
				totals: { expected: 42, worked: 2.5, adjusted: 5, balance: -34.5 },
				endedBalance: null,
				weeks: [
					week("2026-09-07", {
						worked: 2.5,
						contractExpected: 42,
						balanceEnd: null,
						adjustments: [{ id: "a1", date: "2026-09-08", kind: "delta", hours: 5, applied: 5 }],
					}),
				],
			},
		});
		const region = screen.getByRole("region", { name: "Earlier weeks" });
		expect(region).toHaveTextContent("Contract starts Mon Sep 7, 2026 · Full time · 42 h/wk");
		expect(region).toHaveTextContent("No earlier weeks — the contract started this week.");
		expect(within(region).queryByRole("table")).toBeNull();
		expect(within(region).queryByRole("button", { name: "Copy as CSV" })).toBeNull();
		expect(region).toHaveTextContent("All time 2.5 h · 1 session");
		// What it records this week can still be opened, and more added.
		expect(
			within(region).getByRole("button", {
				name: "Change adjustment: Tue Sep 8 · Adjusted +5.0 h",
			}),
		).toHaveTextContent("+5.0");
		await userEvent.click(within(region).getByRole("button", { name: "Adjust balance" }));
		expect(screen.getByRole("dialog", { name: "Adjust balance" })).toBeInTheDocument();
	});
});

describe("WeekLedger on a side project", () => {
	const loom: ProjectWithDuration = {
		...DAY_JOB,
		kind: "side_project",
		contract: undefined,
		weeklyGoal: 8,
		goalOverrides: [{ weekOf: "2026-08-24", weeklyGoal: null }],
	};
	const ledger: Ledger = {
		since: null,
		totals: null,
		endedBalance: null,
		weeks: [
			week("2026-09-07", { effectiveGoal: 8, contractExpected: null, balanceEnd: null }),
			week("2026-08-31", {
				worked: 8.4,
				effectiveGoal: 8,
				contractExpected: null,
				balanceEnd: null,
			}),
			week("2026-08-24", {
				worked: 0,
				days: [0, 0, 0, 0, 0, 0, 0],
				effectiveGoal: null,
				effectiveGoalOverridden: true,
				contractExpected: null,
				balanceEnd: null,
			}),
		],
	};

	it("heads the column Goal, drops Balance, and opens the override popover from the goal cell", async () => {
		renderLedger({ project: loom, ledger });
		const region = screen.getByRole("region", { name: "Earlier weeks" });
		expect(region).toHaveTextContent("Goal");
		expect(region).not.toHaveTextContent("Expected");
		expect(within(region).queryByRole("columnheader", { name: "Balance" })).toBeNull();
		expect(region).not.toHaveTextContent("back to the opening balance");
		expect(within(region).queryByRole("button", { name: "Adjust balance" })).toBeNull();

		const noGoal = within(region).getByRole("button", { name: "No goal" });
		expect(noGoal).toHaveAttribute("title", "Goal override active — click to edit");
		expect(region).toHaveTextContent("override");

		await userEvent.click(within(region).getByRole("button", { name: "8" }));
		expect(screen.getByText("Override goal")).toBeInTheDocument();
		await userEvent.click(screen.getByRole("button", { name: "Save" }));
		expect(overrides).toHaveBeenCalledWith(
			expect.objectContaining({
				projectId: "p1",
				overrides: expect.arrayContaining([
					expect.objectContaining({ week_of: "2026-08-31", weekly_goal: 8 }),
				]),
			}),
			expect.anything(),
		);
	});
});
