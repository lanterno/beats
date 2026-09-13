/**
 * Time off: absences still to come and weekday holidays in one list by date,
 * a run of one type across a weekend or a holiday as one row counted in
 * halves, "Tomorrow" on the first row, next year's dates with their year,
 * the year's tally counting a half day as a half, and what a row opens.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Absence } from "@/entities/absence";
import type { Holiday, ProjectWithDuration } from "@/entities/project";
import { TimeOff, type TimeOffProps } from "./TimeOff";

const { hooks } = vi.hoisted(() => ({
	hooks: { absences: vi.fn(), holidays: vi.fn() },
}));

vi.mock("@/entities/absence", async () => {
	const actual = await vi.importActual<typeof import("@/entities/absence")>("@/entities/absence");
	return {
		...actual,
		useAbsences: () => ({ data: hooks.absences(), isLoading: false, error: null }),
	};
});
vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return {
		...actual,
		useProjectHolidays: (_id: string, year: number) => ({ data: hooks.holidays(year) }),
		useHolidayRegions: () => ({
			data: [{ code: "CH", name: "Switzerland", subdivisions: [{ code: "ZH", name: "Zürich" }] }],
		}),
	};
});

// Thu Sep 10, 2026.
const TODAY = "2026-09-10";

function absence(date: string, type: Absence["type"], extra: Partial<Absence> = {}): Absence {
	return { id: `a-${date}`, projectId: "p1", date, type, halfDay: false, ...extra };
}

const ABSENCES: Absence[] = [
	// Earlier this year: in the tally, not in the list.
	absence("2026-03-03", "sick", { halfDay: true }),
	...["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10"].map((d) =>
		absence(d, "vacation"),
	),
	absence("2026-09-11", "vacation", { note: "Zürich trip" }),
	// Friday, then Monday (half) and Tuesday: one run across the weekend.
	absence("2026-10-06", "vacation"),
	absence("2026-10-02", "vacation"),
	absence("2026-10-05", "vacation", { halfDay: true }),
	// The next day, another type: its own row.
	absence("2026-10-07", "sick"),
	// Wednesday, Thursday, then Monday over Christmas on the Friday.
	absence("2026-12-23", "vacation"),
	absence("2026-12-24", "vacation"),
	absence("2026-12-28", "vacation"),
];

const HOLIDAYS: Record<number, Holiday[]> = {
	2026: [
		{ date: "2026-08-01", name: "Swiss National Day" },
		{ date: "2026-12-25", name: "Christmas Day" },
		{ date: "2026-12-26", name: "St. Stephen's Day" },
	],
	2027: [{ date: "2027-01-01", name: "New Year's Day" }],
};

const PROJECT: ProjectWithDuration = {
	id: "p1",
	name: "Contract Co",
	color: "#5B9CF6",
	archived: false,
	goalOverrides: [],
	autostartRepos: [],
	kind: "day_job",
	contract: {
		terms: [
			{ effectiveFrom: "2026-01-05", scheduleType: "full_time", fullTimeHours: 42, percentage: 1 },
		],
		holidayCountry: "CH",
		holidaySubdivision: "ZH",
		openingBalanceHours: 0,
	},
	totalMinutes: 0,
	weeklyMinutes: 0,
};

function renderTimeOff(overrides: Partial<TimeOffProps> = {}) {
	const props: TimeOffProps = {
		project: PROJECT,
		todayIso: TODAY,
		onBook: vi.fn(),
		onOpenAbsence: vi.fn(),
		onOpenWeek: vi.fn(),
		...overrides,
	};
	render(<TimeOff {...props} />);
	return props;
}

beforeEach(() => {
	hooks.absences.mockReturnValue(ABSENCES);
	hooks.holidays.mockImplementation((year: number) => HOLIDAYS[year] ?? []);
});
afterEach(cleanup);

describe("TimeOff", () => {
	it("lists what is coming by date, runs collapsed, holidays among them, and tallies the year", () => {
		renderTimeOff();
		const region = screen.getByRole("region", { name: "Time off" });
		const rows = within(region)
			.getAllByRole("listitem")
			.map((li) => li.textContent);

		expect(rows).toEqual([
			"Tomorrow · Fri Sep 11Vacation · Zürich tripvacation",
			"Fri Oct 2 – Tue Oct 6Vacation · 2½ daysvacation",
			"Wed Oct 7Sicksick",
			"Wed Dec 23 – Mon Dec 28Vacation · 3 daysvacation",
			// A Saturday holiday costs nothing and is not listed.
			"Fri Dec 25Christmas Day · public holiday · Zürichholiday",
			"Fri Jan 1, 2027New Year's Day · public holiday · Zürichholiday",
		]);
		// 5 in July, 1 + 2½ + 3 to come; a half day and a whole one sick.
		expect(region).toHaveTextContent("2026: 11½ d vacation booked · 1½ d sick");
		expect(region).not.toHaveTextContent("Public holidays appear once");
	});

	it("opens a run in the dialog on its days and a holiday's week in Days", async () => {
		const props = renderTimeOff();

		await userEvent.click(screen.getByRole("button", { name: /Fri Oct 2 – Tue Oct 6/ }));
		// One day of three is a half: the dialog starts on whole days, with no note.
		expect(props.onOpenAbsence).toHaveBeenCalledWith({
			from: "2026-10-02",
			through: "2026-10-06",
			initial: { type: "vacation", halfDay: false, note: "" },
		});
		await userEvent.click(screen.getByRole("button", { name: /Christmas Day/ }));
		expect(props.onOpenWeek).toHaveBeenCalledWith("2026-12-25");
	});

	it("says nothing is booked, and that holidays wait for a region", () => {
		hooks.absences.mockReturnValue([]);
		hooks.holidays.mockReturnValue([]);
		renderTimeOff({ project: { ...PROJECT, contract: undefined } });
		const region = screen.getByRole("region", { name: "Time off" });

		expect(region).toHaveTextContent("Nothing booked yet in 2026");
		expect(region).toHaveTextContent("Public holidays appear once the contract has a region.");
	});
});
