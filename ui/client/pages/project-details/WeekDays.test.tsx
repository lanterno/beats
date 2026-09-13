/**
 * The open week's days: today open and the others toggled by click and
 * keyboard, a governed day's figure and its delta, a day off with its tint,
 * the folded weekend, the running beat's live row, ‹ › and Today, and the
 * session actions reachable without a mouse.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ContractDay, ContractWeek, ProjectWithDuration } from "@/entities/project";
import type { Session } from "@/entities/session";
import { WeekDays, type WeekDaysProps } from "./WeekDays";

const { hooks } = vi.hoisted(() => ({
	hooks: {
		useSessions: vi.fn(),
		updateSession: vi.fn(),
		deleteSession: vi.fn(),
	},
}));

vi.mock("@/entities/session", async () => {
	const actual = await vi.importActual<typeof import("@/entities/session")>("@/entities/session");
	return {
		...actual,
		useSessions: () => hooks.useSessions(),
		useUpdateSession: () => ({ mutateAsync: hooks.updateSession, isPending: false }),
		useDeleteSession: () => ({ mutateAsync: hooks.deleteSession, isPending: false }),
	};
});
vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return { ...actual, useProjects: () => ({ data: [] }) };
});
vi.mock("@/entities/intelligence", () => ({
	useFocusScores: () => ({
		data: [
			{ beat_id: "thu", score: 74, components: { length: 1, peak_hours: 1, fragmentation: 1 } },
		],
	}),
}));
vi.mock("@/entities/planning", () => ({
	useProjectPlannedByWeek: () => ({ byMondayIso: new Map([["2026-09-07", 28]]) }),
}));
vi.mock("@/entities/github", () => ({
	useProjectGitActivityByWeek: () => ({ byMondayIso: new Map([["2026-09-07", 9]]) }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const TODAY = "2026-09-10";
const WEEK_OF = "2026-09-07";

const PROJECT: ProjectWithDuration = {
	id: "p1",
	name: "Contract Co",
	color: "#5B9CF6",
	archived: false,
	goalOverrides: [],
	autostartRepos: [],
	kind: "day_job",
	githubRepo: "acme/backend",
	contract: {
		terms: [
			{
				effectiveFrom: "2026-01-05",
				scheduleType: "part_time",
				fullTimeHours: 42,
				percentage: 0.8,
			},
		],
		openingBalanceHours: 0,
	},
	totalMinutes: 0,
	weeklyMinutes: 0,
};

/** A local wall-clock moment on a day of the open week, as the API's UTC ISO. */
function at(day: number, hour: number, minute: number): string {
	return new Date(2026, 8, day, hour, minute).toISOString();
}

function session(
	id: string,
	start: string,
	minutes: number,
	extra: Partial<Session> = {},
): Session {
	return {
		id,
		projectId: "p1",
		startTime: start,
		endTime: new Date(new Date(start).getTime() + minutes * 60_000).toISOString(),
		duration: minutes,
		note: "",
		tags: [],
		...extra,
	};
}

const SESSIONS = [
	session("mon1", at(7, 8, 52), 168),
	session("mon2", at(7, 12, 30), 155),
	session("mon3", at(7, 15, 20), 104),
	session("thu", at(10, 8, 47), 185, { note: "standup, PR reviews", tags: ["review"] }),
];

const PER_DAY = 6.72;
function days(patches: Record<number, Partial<ContractDay>>): ContractDay[] {
	return [0, 1, 2, 3, 4, 5, 6].map((i) => ({
		date: `2026-09-${String(7 + i).padStart(2, "0")}`,
		expected: i < 5 ? PER_DAY : 0,
		worked: 0,
		...patches[i],
	}));
}
const CONTRACT_WEEK: ContractWeek = {
	weekOf: WEEK_OF,
	expected: 26.88,
	worked: 10.5,
	remaining: 16.38,
	days: days({
		0: { worked: 7.1 },
		3: { worked: 3.4 },
		4: { expected: 0, absence: { type: "vacation", halfDay: false, note: "Zürich trip" } },
	}),
};

function renderDays(overrides: Partial<WeekDaysProps> = {}) {
	const props: WeekDaysProps = {
		project: PROJECT,
		todayIso: TODAY,
		weekOf: WEEK_OF,
		onWeekChange: vi.fn(),
		contractWeek: CONTRACT_WEEK,
		running: null,
		onChangeAbsence: vi.fn(),
		...overrides,
	};
	render(<WeekDays {...props} />);
	return props;
}

/** A day's toggle, named by the day ("Mon 7"). */
function row(name: string) {
	return screen.getByRole("button", { name: new RegExp(`^${name} \\d`) });
}

/** The whole day row around its toggle: the name, what happened, the figure. */
function dayRow(name: string) {
	return row(name).closest("[data-day]");
}

beforeEach(() => {
	hooks.useSessions.mockReturnValue({ data: SESSIONS, refetch: vi.fn() });
	hooks.updateSession.mockReset();
	hooks.deleteSession.mockReset();
});
afterEach(cleanup);

describe("WeekDays", () => {
	it("opens today by default and the other days on click, Enter and Space", async () => {
		renderDays();
		const region = screen.getByRole("region", { name: "Days" });
		expect(region).toHaveTextContent("Sep 7 – 13 · W37");

		const thu = row("Thu");
		expect(thu).toHaveAttribute("aria-expanded", "true");
		expect(thu).toHaveTextContent("today");
		expect(region).toHaveTextContent("08:47 → 11:52");
		expect(region).toHaveTextContent("standup, PR reviews");
		expect(region).toHaveTextContent("#review");
		expect(region).toHaveTextContent("◦ 74");
		expect(region).toHaveTextContent("3h 05m");

		const mon = row("Mon");
		expect(mon).toHaveAttribute("aria-expanded", "false");
		expect(region).not.toHaveTextContent("08:52 → 11:40");
		await userEvent.click(mon);
		expect(mon).toHaveAttribute("aria-expanded", "true");
		expect(region).toHaveTextContent("08:52 → 11:40");

		mon.focus();
		await userEvent.keyboard("{Enter}");
		expect(mon).toHaveAttribute("aria-expanded", "false");
		await userEvent.keyboard(" ");
		expect(mon).toHaveAttribute("aria-expanded", "true");
	});

	it("reads each day's figure off the contract week, tints a day off and folds the weekend", () => {
		const props = renderDays();
		const region = screen.getByRole("region", { name: "Days" });

		expect(dayRow("Mon")).toHaveTextContent("3 sessions");
		expect(dayRow("Mon")).toHaveTextContent("7.1 of 6.7+0.4");
		// Today is not closed: the figure, no delta yet.
		expect(dayRow("Thu")).toHaveTextContent("3.4 of 6.7");
		expect(dayRow("Thu")).not.toHaveTextContent("−3.3");
		expect(region).toHaveTextContent("— of 6.7");

		const fri = within(region).getByText("Vacation · Zürich trip").closest("[data-day]");
		expect(fri).toHaveTextContent("nothing expected");
		screen.getByRole("button", { name: "Change" }).click();
		expect(props.onChangeAbsence).toHaveBeenCalledWith("2026-09-11", {
			type: "vacation",
			halfDay: false,
			note: "Zürich trip",
		});

		expect(region).toHaveTextContent("Sat–Sun 12–13");
		expect(region).not.toHaveTextContent(/Sun\s*13\b/);
		expect(region).toHaveTextContent("Planned 28 h");
		expect(region).toHaveTextContent("9 commits");
	});

	it("keeps Change its own control on a day off that also has sessions", async () => {
		// Monday: sick half a day, and 7.1 h worked around it.
		const props = renderDays({
			contractWeek: {
				...CONTRACT_WEEK,
				days: days({
					0: { worked: 7.1, expected: 3.36, absence: { type: "sick", halfDay: true } },
					3: { worked: 3.4 },
				}),
			},
		});
		const mon = row("Mon");
		const change = screen.getByRole("button", { name: "Change" });

		change.focus();
		await userEvent.keyboard("{Enter}");
		expect(props.onChangeAbsence).toHaveBeenCalledTimes(1);
		expect(mon).toHaveAttribute("aria-expanded", "false");

		await userEvent.click(change);
		expect(props.onChangeAbsence).toHaveBeenCalledTimes(2);
		expect(mon).toHaveAttribute("aria-expanded", "false");
	});

	it("offers Book time off on a governed weekday with nothing off, next after the day by keyboard", async () => {
		const onBookTimeOff = vi.fn();
		renderDays({ onBookTimeOff });
		// Friday is already off; its row changes the absence instead.
		expect(screen.queryByRole("button", { name: /Book time off on Fri/ })).not.toBeInTheDocument();

		row("Mon").focus();
		await userEvent.tab();
		const book = screen.getByRole("button", { name: "Book time off on Mon 7" });
		expect(book).toHaveFocus();
		await userEvent.keyboard("{Enter}");
		expect(onBookTimeOff).toHaveBeenCalledWith("2026-09-07");
		expect(row("Mon")).toHaveAttribute("aria-expanded", "false");
	});

	it("keeps today's own row when today is on the weekend", () => {
		renderDays({ todayIso: "2026-09-13" });
		expect(screen.getByRole("region", { name: "Days" })).toHaveTextContent("Sun 13 today");
		expect(screen.getByRole("region", { name: "Days" })).not.toHaveTextContent("Sat–Sun");
	});

	it("shows the running beat as a live row on today and in the foot", () => {
		renderDays({ running: { since: at(10, 13, 10) } });
		const region = screen.getByRole("region", { name: "Days" });
		expect(dayRow("Thu")).toHaveTextContent("1 session · running");
		expect(region).toHaveTextContent("13:10 → now");
		expect(region).toHaveTextContent("Timer running since 13:10");
	});

	it("moves the open week with ‹ › and back with Today", async () => {
		const props = renderDays();
		await userEvent.click(screen.getByRole("button", { name: "Previous week" }));
		expect(props.onWeekChange).toHaveBeenLastCalledWith("2026-08-31");
		await userEvent.click(screen.getByRole("button", { name: "Next week" }));
		expect(props.onWeekChange).toHaveBeenLastCalledWith("2026-09-14");
		expect(screen.queryByRole("button", { name: "Today" })).not.toBeInTheDocument();
		cleanup();

		const past = renderDays({ weekOf: "2026-08-31", contractWeek: undefined });
		await userEvent.click(screen.getByRole("button", { name: "Today" }));
		expect(past.onWeekChange).toHaveBeenLastCalledWith("2026-09-07");
	});

	it("keeps edit and delete reachable by keyboard, with a confirm before deleting", async () => {
		hooks.deleteSession.mockResolvedValue(undefined);
		renderDays();

		await userEvent.click(screen.getByRole("button", { name: "Delete session" }));
		await userEvent.click(screen.getByRole("button", { name: "Delete" }));
		expect(hooks.deleteSession).toHaveBeenCalledWith("thu");

		await userEvent.click(screen.getByRole("button", { name: "Edit session" }));
		expect(screen.getByLabelText("Start")).toBeInTheDocument();
	});

	it("shows worked alone on a project the contract does not govern, with nothing to book", () => {
		renderDays({
			onBookTimeOff: vi.fn(),
			project: { ...PROJECT, kind: "side_project", contract: undefined },
			contractWeek: undefined,
			ledgerWeek: {
				weekOf: WEEK_OF,
				worked: 10.5,
				days: [7.1, 0, 0, 3.4, 0, 0, 0],
				effectiveGoal: 8,
				effectiveGoalType: "target",
				effectiveGoalOverridden: false,
				contractExpected: null,
				balanceEnd: null,
				notes: [],
			},
		});
		expect(dayRow("Mon")).toHaveTextContent("7.1 h");
		expect(dayRow("Mon")).not.toHaveTextContent("of");
		expect(screen.getByRole("region", { name: "Days" })).not.toHaveTextContent("nothing expected");
		expect(screen.queryByRole("button", { name: /Book time off/ })).not.toBeInTheDocument();
	});
});
