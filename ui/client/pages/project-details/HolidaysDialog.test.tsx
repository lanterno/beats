/**
 * The Holidays dialog: unticking a public holiday sends its date as not
 * given, a company day without a name is refused before anything is sent,
 * another year's entries go out untouched, a date not given that is no
 * longer a holiday of the region is listed and can be removed, and a 422 on
 * a company day lands on its row.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Contract, Holiday } from "@/entities/project";
import { ApiError } from "@/shared/api";
import { HolidaysDialog } from "./HolidaysDialog";

const { hooks } = vi.hoisted(() => ({
	hooks: { mutate: vi.fn(), holidays: vi.fn() },
}));

vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return {
		...actual,
		useUpdateContract: () => ({ mutate: hooks.mutate, isPending: false }),
		useHolidayRegions: () => ({
			data: [{ code: "CH", name: "Switzerland", subdivisions: [{ code: "ZH", name: "Zürich" }] }],
		}),
		useProjectHolidays: (_id: string, year: number, options: { includeNotGiven?: boolean }) => ({
			data: options.includeNotGiven ? hooks.holidays(year) : [],
			isLoading: false,
		}),
	};
});
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// Thu Sep 10, 2026.
const TODAY = "2026-09-10";

function holiday(date: string, name: string, given = true): Holiday {
	return { date, name, source: "region", given };
}

const ZURICH_2026: Holiday[] = [
	holiday("2026-08-01", "Swiss National Day"), // a Saturday
	holiday("2026-12-25", "Christmas Day"),
];

const CONTRACT: Contract = {
	terms: [
		{ effectiveFrom: "2026-01-05", scheduleType: "full_time", fullTimeHours: 42, percentage: 1 },
	],
	holidayCountry: "CH",
	holidaySubdivision: "ZH",
	openingBalanceHours: 0,
	companyHolidays: [],
	holidaysNotGiven: [],
};

function renderDialog(contract: Partial<Contract> = {}) {
	const onClose = vi.fn();
	render(
		<HolidaysDialog
			project={{ id: "p1", contract: { ...CONTRACT, ...contract } }}
			todayIso={TODAY}
			onClose={onClose}
		/>,
	);
	return onClose;
}

const dialog = () => screen.getByRole("dialog");
const sentContract = () => hooks.mutate.mock.calls[0][0].contract;

beforeEach(() => {
	hooks.mutate.mockReset();
	hooks.holidays.mockImplementation((year: number) => (year === 2026 ? ZURICH_2026 : []));
});
afterEach(cleanup);

describe("HolidaysDialog", () => {
	it("sends an unticked public holiday as not given, and another year's days untouched", async () => {
		const nextYear = { date: "2027-12-24", name: "Christmas Eve" };
		renderDialog({ companyHolidays: [nextYear] });

		// A weekend holiday costs nothing either way: no tick to give.
		expect(dialog()).toHaveTextContent("on a weekend — costs nothing");
		expect(
			within(dialog()).queryByRole("checkbox", { name: /Swiss National Day/ }),
		).not.toBeInTheDocument();
		// The 2027 day is not on this year's page.
		expect(within(dialog()).queryByDisplayValue("Christmas Eve")).not.toBeInTheDocument();

		await userEvent.click(within(dialog()).getByRole("checkbox", { name: /Christmas Day/ }));
		await userEvent.click(within(dialog()).getByRole("button", { name: "Save" }));

		expect(hooks.mutate).toHaveBeenCalledTimes(1);
		expect(sentContract().holidays_not_given).toEqual(["2026-12-25"]);
		expect(sentContract().company_holidays).toEqual([nextYear]);
	});

	it("keeps a tick on a weekend holiday stored as not given, so it can be taken back", async () => {
		// The dialog never builds this, but the API accepts it; without the tick
		// the date would be counted in the constants and impossible to remove.
		hooks.holidays.mockReturnValue([holiday("2026-08-01", "Swiss National Day", false)]);
		renderDialog({ holidaysNotGiven: ["2026-08-01"] });

		const tick = within(dialog()).getByRole("checkbox", { name: /Swiss National Day/ });
		expect(tick).not.toBeChecked();
		await userEvent.click(tick);
		await userEvent.click(within(dialog()).getByRole("button", { name: "Save" }));

		expect(sentContract().holidays_not_given).toEqual([]);
	});

	it("refuses a company day without a name before sending anything", async () => {
		renderDialog();

		await userEvent.click(within(dialog()).getByRole("button", { name: "Add a day" }));
		fireEvent.change(within(dialog()).getByLabelText("Company holiday 1: date"), {
			target: { value: "2026-12-24" },
		});
		await userEvent.click(within(dialog()).getByRole("button", { name: "Save" }));

		expect(hooks.mutate).not.toHaveBeenCalled();
		expect(dialog()).toHaveTextContent("Name the day");
	});

	it("lists a date not given that the region no longer has, and removing it drops it", async () => {
		renderDialog({ holidaysNotGiven: ["2026-03-04"] });

		const leftover = within(dialog()).getByRole("region", { name: "No longer a holiday here" });
		expect(leftover).toHaveTextContent("Wed Mar 4 · not a holiday in Zürich");

		await userEvent.click(within(leftover).getByRole("button", { name: /Remove Wed Mar 4/ }));
		expect(
			within(dialog()).queryByRole("region", { name: "No longer a holiday here" }),
		).not.toBeInTheDocument();
		await userEvent.click(within(dialog()).getByRole("button", { name: "Save" }));

		expect(sentContract().holidays_not_given).toEqual([]);
	});

	it("puts a 422 on a company day's name beside that row", async () => {
		hooks.mutate.mockImplementation((_vars, options: { onError: (err: unknown) => void }) =>
			options.onError(
				new ApiError(422, "Validation failed", "VALIDATION_ERROR", [
					{
						path: "company_holidays.0.name",
						message: "String should have at most 80 characters",
						type: "string_too_long",
					},
				]),
			),
		);
		renderDialog({ companyHolidays: [{ date: "2026-12-24", name: "Christmas Eve" }] });

		await userEvent.click(within(dialog()).getByRole("button", { name: "Save" }));

		const name = within(dialog()).getByLabelText("Company holiday 1: name");
		expect(name).toHaveAttribute("aria-invalid", "true");
		expect(name).toHaveAccessibleDescription("String should have at most 80 characters");
		expect(within(dialog()).queryByRole("alert")).not.toBeInTheDocument();
	});
});
