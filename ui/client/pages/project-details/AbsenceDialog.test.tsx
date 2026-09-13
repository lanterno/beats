/**
 * The booking dialog: the grid sets From then Through and moves between
 * months; a range goes out as one run of writes — the weekend and a public
 * holiday skipped, half day and a typed note on every day — and a partial
 * failure says how many were saved; the cost line counts what is already
 * booked; a booked day keeps its own note unless one is typed; Remove takes
 * a booked range, and a holiday holding an absence; and nothing closes the
 * dialog while a run is saving.
 */
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Absence, AbsenceInput } from "@/entities/absence";
import type { Contract, ContractWeek } from "@/entities/project";
import { AbsenceDialog, type AbsenceDialogProps } from "./AbsenceDialog";

const { hooks } = vi.hoisted(() => ({
	hooks: {
		absences: vi.fn(),
		record: vi.fn(),
		remove: vi.fn(),
		week: vi.fn(),
	},
}));

vi.mock("@/entities/absence", async () => {
	const actual = await vi.importActual<typeof import("@/entities/absence")>("@/entities/absence");
	return {
		...actual,
		useAbsences: () => ({ data: hooks.absences(), isLoading: false }),
		useRecordAbsences: () => ({ mutateAsync: hooks.record }),
		useRemoveAbsences: () => ({ mutateAsync: hooks.remove }),
	};
});
vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return {
		...actual,
		useProjectHolidays: () => ({
			data: [{ date: "2026-09-21", name: "Knabenschiessen" }],
			isLoading: false,
		}),
		useContractWeek: (_id: string, weekOf: string, options: { enabled?: boolean }) => ({
			data: options.enabled ? hooks.week(weekOf) : undefined,
		}),
	};
});
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// Thu Sep 10, 2026; 80 % of 42 h, 6.72 h a weekday.
const TODAY = "2026-09-10";
const CONTRACT: Contract = {
	terms: [
		{ effectiveFrom: "2026-01-05", scheduleType: "part_time", fullTimeHours: 42, percentage: 0.8 },
	],
	holidayCountry: "CH",
	holidaySubdivision: "ZH",
	openingBalanceHours: 0,
};
const THIS_WEEK: Pick<ContractWeek, "weekOf" | "expected"> = {
	weekOf: "2026-09-07",
	expected: 33.6,
};
const VACATION = { type: "vacation", halfDay: false } as const;

function renderDialog(overrides: Partial<AbsenceDialogProps> = {}) {
	const props: AbsenceDialogProps = {
		project: { id: "p1", contract: CONTRACT },
		todayIso: TODAY,
		from: "2026-09-11",
		onClose: vi.fn(),
		...overrides,
	};
	render(<AbsenceDialog {...props} />);
	return props;
}

function booked(id: string, date: string, extra: Partial<Absence> = {}): Absence {
	return { id, projectId: "p1", date, ...VACATION, ...extra };
}

const dialog = () => screen.getByRole("dialog");
const cost = () => within(dialog()).getByText(/weekday|Nothing|Counts once/);
const button = (name: string | RegExp) => within(dialog()).getByRole("button", { name });
const sent = (): AbsenceInput[] => hooks.record.mock.calls[0][0].inputs;

beforeEach(() => {
	vi.clearAllMocks();
	hooks.absences.mockReturnValue([]);
	hooks.record.mockImplementation(async ({ inputs }: { inputs: AbsenceInput[] }) => ({
		done: inputs.length,
		error: null,
	}));
	hooks.remove.mockImplementation(async ({ absenceIds }: { absenceIds: string[] }) => ({
		done: absenceIds.length,
		error: null,
	}));
	hooks.week.mockImplementation((weekOf: string) =>
		weekOf === "2026-09-07" ? THIS_WEEK : undefined,
	);
});
afterEach(cleanup);

describe("AbsenceDialog", () => {
	it("books a range weekday by weekday, skipping the weekend and a public holiday", async () => {
		const props = renderDialog();

		await userEvent.click(button("Sick"));
		// From on the first click, Through on the second.
		await userEvent.click(button(/^Fri Sep 18, 2026/));
		await userEvent.click(button(/^Tue Sep 22, 2026/));
		expect(within(dialog()).getByLabelText("From")).toHaveValue("2026-09-18");
		expect(within(dialog()).getByLabelText("Through")).toHaveValue("2026-09-22");
		expect(cost()).toHaveTextContent(
			"The expectation drops by 13.4 h. Two weekdays; weekends and public holidays are skipped.",
		);
		// Half days cost half: two of them one day's hours.
		await userEvent.click(within(dialog()).getByRole("checkbox", { name: "Half day" }));
		expect(cost()).toHaveTextContent("The expectation drops by 6.7 h.");
		await userEvent.type(within(dialog()).getByLabelText("Note"), "flu");

		await userEvent.click(button("Save"));

		await waitFor(() => expect(props.onClose).toHaveBeenCalled());
		expect(hooks.record).toHaveBeenCalledTimes(1);
		expect(hooks.record.mock.calls[0][0]).toEqual({
			projectId: "p1",
			inputs: [
				{ date: "2026-09-18", type: "sick", halfDay: true, note: "flu" },
				{ date: "2026-09-22", type: "sick", halfDay: true, note: "flu" },
			],
		});
		expect(toast.success).toHaveBeenCalledWith("2 days booked");
	});

	it("says how many days were saved when a write fails partway", async () => {
		hooks.record.mockResolvedValueOnce({ done: 1, error: new Error("offline") });
		const props = renderDialog({ from: "2026-09-14", through: "2026-09-16" });

		await userEvent.click(button("Save"));

		await waitFor(() => expect(toast.error).toHaveBeenCalled());
		expect(sent()).toHaveLength(3);
		expect(vi.mocked(toast.error).mock.calls[0][0]).toMatch(/^1 of 3 days saved/);
		expect(props.onClose).not.toHaveBeenCalled();
	});

	it("does not close while a run is saving", async () => {
		let finish: (writes: { done: number; error: null }) => void = () => {};
		hooks.record.mockImplementationOnce(
			() =>
				new Promise((resolve) => {
					finish = resolve;
				}),
		);
		const props = renderDialog();

		await userEvent.click(button("Save"));
		expect(button("Cancel")).toBeDisabled();
		await userEvent.keyboard("{Escape}");
		expect(props.onClose).not.toHaveBeenCalled();

		finish({ done: 1, error: null });
		await waitFor(() => expect(props.onClose).toHaveBeenCalledTimes(1));
	});

	it("says what the booking costs the week, or why it costs nothing", () => {
		renderDialog();
		expect(cost()).toHaveTextContent(
			"This week's expectation drops by 6.7 h, to 26.9 h. One weekday; weekends and public holidays are skipped.",
		);
		cleanup();

		renderDialog({
			project: {
				id: "p1",
				contract: {
					...CONTRACT,
					terms: [{ effectiveFrom: "2026-01-05", scheduleType: "objective" }],
				},
			},
		});
		expect(cost()).toHaveTextContent("Nothing is due under this term; the day is recorded.");
		cleanup();

		renderDialog({ project: { id: "p1", contract: undefined } });
		expect(cost()).toHaveTextContent("Counts once a contract is set.");
	});

	it("counts a change against what the day already holds, and removes it by id", async () => {
		hooks.absences.mockReturnValue([booked("a1", "2026-09-11", { note: "Zürich trip" })]);
		const props = renderDialog({ initial: { ...VACATION, note: "Zürich trip" } });

		expect(within(dialog()).getByLabelText("Note")).toHaveValue("Zürich trip");
		expect(cost()).toHaveTextContent("This week's expectation stays as it is.");
		await userEvent.click(within(dialog()).getByRole("checkbox", { name: "Half day" }));
		expect(cost()).toHaveTextContent("This week's expectation rises by 3.4 h, to 37.0 h.");

		await userEvent.click(button("Remove"));

		await waitFor(() => expect(props.onClose).toHaveBeenCalled());
		expect(hooks.remove).toHaveBeenCalledWith({ projectId: "p1", absenceIds: ["a1"] });
		expect(hooks.record).not.toHaveBeenCalled();
	});

	it("keeps each booked day's own note unless one is typed", async () => {
		hooks.absences.mockReturnValue([
			booked("a14", "2026-09-14", { note: "Zürich trip" }),
			booked("a15", "2026-09-15"),
		]);
		const range = { from: "2026-09-14", through: "2026-09-16", initial: { ...VACATION, note: "" } };
		renderDialog(range);

		expect(within(dialog()).getByLabelText("Note")).toHaveAttribute(
			"placeholder",
			"Different notes — typing replaces them",
		);
		await userEvent.click(within(dialog()).getByRole("checkbox", { name: "Half day" }));
		await userEvent.click(button("Save"));
		await waitFor(() => expect(hooks.record).toHaveBeenCalled());
		// Wednesday was not booked: it takes the field, empty.
		expect(sent().map((input) => input.note)).toEqual(["Zürich trip", "", ""]);
		cleanup();
		hooks.record.mockClear();

		renderDialog(range);
		await userEvent.type(within(dialog()).getByLabelText("Note"), "Ticino");
		await userEvent.click(button("Save"));
		await waitFor(() => expect(hooks.record).toHaveBeenCalled());
		expect(sent().map((input) => input.note)).toEqual(["Ticino", "Ticino", "Ticino"]);
	});

	it("removes a whole range only when every weekday in it is booked", async () => {
		hooks.absences.mockReturnValue([
			booked("a14", "2026-09-14"),
			booked("a15", "2026-09-15"),
			booked("a16", "2026-09-16"),
		]);
		const props = renderDialog({ from: "2026-09-14", through: "2026-09-16", initial: VACATION });

		await userEvent.click(button("Remove 3 days"));

		await waitFor(() => expect(props.onClose).toHaveBeenCalled());
		expect(hooks.remove).toHaveBeenCalledWith({
			projectId: "p1",
			absenceIds: ["a14", "a15", "a16"],
		});
		cleanup();

		// Thursday is not booked: nothing to take back as a whole.
		renderDialog({ from: "2026-09-14", through: "2026-09-17" });
		expect(within(dialog()).queryByRole("button", { name: /^Remove/ })).not.toBeInTheDocument();
	});

	it("offers Remove on a public holiday holding an absence, though nothing there is bookable", async () => {
		hooks.absences.mockReturnValue([booked("a21", "2026-09-21")]);
		const props = renderDialog({ from: "2026-09-21", initial: VACATION });

		expect(cost()).toHaveTextContent("Nothing to book");
		expect(button("Save")).toBeDisabled();
		await userEvent.click(button("Remove"));

		await waitFor(() => expect(props.onClose).toHaveBeenCalled());
		expect(hooks.remove).toHaveBeenCalledWith({ projectId: "p1", absenceIds: ["a21"] });
	});

	it("moves the grid between months, where weekends are not buttons", async () => {
		renderDialog();
		expect(dialog()).toHaveTextContent("September 2026");

		await userEvent.click(button("Next month"));

		expect(dialog()).toHaveTextContent("October 2026");
		expect(
			within(dialog()).queryByRole("button", { name: /^Sat Oct 3, 2026/ }),
		).not.toBeInTheDocument();
		await userEvent.click(button(/^Mon Oct 5, 2026/));
		expect(within(dialog()).getByLabelText("From")).toHaveValue("2026-10-05");
	});
});
