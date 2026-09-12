import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AbsenceCalendar } from "./AbsenceCalendar";

const record = vi.fn();
const remove = vi.fn();
const useAbsencesMock = vi.fn();
const useProjectHolidaysMock = vi.fn();

vi.mock("@/entities/absence", async () => {
	const actual = await vi.importActual<typeof import("@/entities/absence")>("@/entities/absence");
	return {
		...actual,
		useAbsences: () => useAbsencesMock(),
		useRecordAbsence: () => ({ mutate: record, isPending: false }),
		useRemoveAbsence: () => ({ mutate: remove, isPending: false }),
	};
});
vi.mock("@/entities/project", () => ({
	useProjectHolidays: () => useProjectHolidaysMock(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// April 2026: the 1st is a Wednesday, Easter Monday is the 6th.
const APRIL = new Date(2026, 3, 15);
// The heading is the runner's locale's; the test asks Intl the same question.
const monthLabel = (d: Date) => d.toLocaleDateString(undefined, { month: "long", year: "numeric" });

describe("AbsenceCalendar", () => {
	beforeEach(() => {
		record.mockReset();
		remove.mockReset();
		useProjectHolidaysMock.mockReturnValue({
			data: [{ date: "2026-04-06", name: "Easter Monday" }],
		});
		useAbsencesMock.mockReturnValue({
			data: [
				{
					id: "a1",
					projectId: "p1",
					date: "2026-04-14",
					halfDay: true,
					type: "vacation",
					note: "Dentist",
				},
			],
			error: null,
		});
	});
	afterEach(cleanup);

	it("marks a holiday with its name and keeps it out of the buttons", () => {
		render(<AbsenceCalendar projectId="p1" initialMonth={APRIL} />);
		expect(screen.getByText("Easter Monday").closest("button")).toBeNull();
		// Weekends are not buttons either — the contract owes nothing on them:
		// 30 days, less 8 weekend days and the holiday.
		expect(
			screen.getAllByRole("button", { name: /record an absence|Change or remove/ }),
		).toHaveLength(21);
	});

	it("records an absence on the clicked weekday", async () => {
		render(<AbsenceCalendar projectId="p1" initialMonth={APRIL} />);

		await userEvent.click(screen.getByRole("button", { name: /\b15\b.*record an absence/ }));
		const dialog = screen.getByRole("dialog");
		await userEvent.click(within(dialog).getByRole("radio", { name: "Sick" }));
		await userEvent.click(within(dialog).getByLabelText("Half day"));
		await userEvent.click(within(dialog).getByRole("button", { name: "Record absence" }));

		expect(record).toHaveBeenCalledTimes(1);
		expect(record.mock.calls[0][0]).toEqual({
			projectId: "p1",
			input: { date: "2026-04-15", type: "sick", halfDay: true, note: "" },
		});
	});

	it("names an existing absence on its day and removes it by id", async () => {
		render(<AbsenceCalendar projectId="p1" initialMonth={APRIL} />);

		const cell = screen.getByRole("button", { name: /\b14\b.*Vacation, half day — Dentist/ });
		await userEvent.click(cell);
		await userEvent.click(
			within(screen.getByRole("dialog")).getByRole("button", { name: "Remove" }),
		);

		expect(remove).toHaveBeenCalledTimes(1);
		expect(remove.mock.calls[0][0]).toEqual({ projectId: "p1", absenceId: "a1" });
		expect(record).not.toHaveBeenCalled();
	});

	it("moves between months", async () => {
		render(<AbsenceCalendar projectId="p1" initialMonth={APRIL} />);
		expect(screen.getByText(monthLabel(APRIL))).toBeInTheDocument();
		await userEvent.click(screen.getByRole("button", { name: "Next month" }));
		expect(screen.getByText(monthLabel(new Date(2026, 4, 1)))).toBeInTheDocument();
	});
});
