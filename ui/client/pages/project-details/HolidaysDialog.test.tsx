/**
 * The Holidays dialog: unticking a public holiday sends its date as not
 * given, a company day without a name, on another's date or on a date not
 * given is refused before anything is sent (the last with the mark cleared
 * from its row, and a refusal on another year's page opens that year),
 * another year's entries go out untouched, a date not given that is no
 * longer a holiday of the region is listed and can be removed — but only once
 * the year's calendar is in — a 422 on a company day lands on its row, and
 * last year's company days copy into the year shown as rows still to save,
 * offered only when that year has one.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Contract, Holiday } from "@/entities/project";
import { ApiError } from "@/shared/api";
import { HolidaysDialog } from "./HolidaysDialog";

const { hooks } = vi.hoisted(() => ({
	hooks: {
		mutate: vi.fn(),
		holidays: vi.fn(),
		// How the year's read stands: "loaded", still "loading", or the error it failed with.
		read: "loaded" as "loaded" | "loading" | Error,
	},
}));

vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return {
		...actual,
		useUpdateContract: () => ({ mutate: hooks.mutate, isPending: false }),
		useHolidayRegions: () => ({
			data: [{ code: "CH", name: "Switzerland", subdivisions: [{ code: "ZH", name: "Zürich" }] }],
		}),
		useProjectHolidays: (_id: string, year: number, options: { includeNotGiven?: boolean }) =>
			hooks.read === "loaded"
				? {
						data: options.includeNotGiven ? hooks.holidays(year) : [],
						isLoading: false,
						error: null,
					}
				: hooks.read === "loading"
					? { data: undefined, isLoading: true, error: null }
					: { data: undefined, isLoading: false, error: hooks.read },
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
	hooks.read = "loaded";
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

	it("refuses two company days on one date", async () => {
		renderDialog({ companyHolidays: [{ date: "2026-12-24", name: "Christmas Eve" }] });

		await userEvent.click(within(dialog()).getByRole("button", { name: "Add a day" }));
		fireEvent.change(within(dialog()).getByLabelText("Company holiday 2: date"), {
			target: { value: "2026-12-24" },
		});
		fireEvent.change(within(dialog()).getByLabelText("Company holiday 2: name"), {
			target: { value: "Eve again" },
		});
		await userEvent.click(within(dialog()).getByRole("button", { name: "Save" }));

		expect(hooks.mutate).not.toHaveBeenCalled();
		expect(within(dialog()).getByLabelText("Company holiday 2: date")).toHaveAccessibleDescription(
			"Another company holiday is on this day",
		);
		expect(within(dialog()).getByLabelText("Company holiday 1: date")).not.toHaveAttribute(
			"aria-invalid",
		);
	});

	it("shows a public holiday not given that a company day covers, and clears the mark from the row", async () => {
		// The API accepts this shape and lists the date twice; the dialog never builds it.
		hooks.holidays.mockReturnValue([
			holiday("2026-12-25", "Christmas Day", false),
			{ date: "2026-12-25", name: "Firm Christmas", source: "company", given: true },
		]);
		const firm = { date: "2026-12-25", name: "Firm Christmas" };
		renderDialog({ companyHolidays: [firm], holidaysNotGiven: ["2026-12-25"] });

		// Christmas is the region's, unticked: not a left-over removal.
		expect(within(dialog()).getByRole("checkbox", { name: /Christmas Day/ })).not.toBeChecked();
		expect(
			within(dialog()).queryByRole("region", { name: "No longer a holiday here" }),
		).not.toBeInTheDocument();

		await userEvent.click(within(dialog()).getByRole("button", { name: "Save" }));
		expect(hooks.mutate).not.toHaveBeenCalled();
		expect(within(dialog()).getByLabelText("Company holiday 1: date")).toHaveAccessibleDescription(
			"This day is marked as a holiday not given",
		);

		await userEvent.click(
			within(dialog()).getByRole("button", { name: "Clear the mark on Fri Dec 25" }),
		);
		expect(within(dialog()).getByRole("checkbox", { name: /Christmas Day/ })).toBeChecked();
		await userEvent.click(within(dialog()).getByRole("button", { name: "Save" }));

		expect(hooks.mutate).toHaveBeenCalledTimes(1);
		expect(sentContract().holidays_not_given).toEqual([]);
		expect(sentContract().company_holidays).toEqual([firm]);
	});

	it("moves to the year of a refused row on another page", async () => {
		renderDialog({
			companyHolidays: [{ date: "2027-12-24", name: "Christmas Eve" }],
			holidaysNotGiven: ["2027-12-24"],
		});
		expect(within(dialog()).queryByDisplayValue("Christmas Eve")).not.toBeInTheDocument();

		await userEvent.click(within(dialog()).getByRole("button", { name: "Save" }));

		expect(hooks.mutate).not.toHaveBeenCalled();
		expect(dialog()).toHaveTextContent("2027");
		expect(within(dialog()).getByDisplayValue("Christmas Eve")).toBeInTheDocument();
		expect(within(dialog()).getByLabelText("Company holiday 1: date")).toHaveAttribute(
			"aria-invalid",
			"true",
		);
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

	it("lists no date as left over while the year's calendar is loading", () => {
		hooks.read = "loading";
		renderDialog({ holidaysNotGiven: ["2026-12-25"] });

		expect(dialog()).toHaveTextContent("Loading…");
		expect(
			within(dialog()).queryByRole("region", { name: "No longer a holiday here" }),
		).not.toBeInTheDocument();
	});

	it("says the calendar failed to load rather than that the year has no holidays", () => {
		hooks.read = new ApiError(400, "Unknown holiday region CH-ZH", "UNKNOWN_HOLIDAY_REGION");
		renderDialog({ holidaysNotGiven: ["2026-12-25"] });

		const publicList = within(dialog()).getByRole("region", { name: /Public holidays/ });
		expect(within(publicList).getByRole("alert")).toHaveTextContent("Unknown holiday region CH-ZH");
		expect(publicList).not.toHaveTextContent("None in 2026.");
		expect(
			within(dialog()).queryByRole("region", { name: "No longer a holiday here" }),
		).not.toBeInTheDocument();
	});

	it("copies last year's company days into the year shown, unsaved, and says what it left out", async () => {
		const lastYear = [
			{ date: "2025-10-31", name: "Bridge day" }, // a Friday; a Saturday in 2026
			{ date: "2025-12-24", name: "Christmas Eve" },
			{ date: "2025-12-25", name: "Firm Christmas" }, // Zürich's Christmas Day in 2026
			{ date: "2025-12-31", name: "New Year's Eve" },
		];
		const silvester = { date: "2026-12-31", name: "Silvester" };
		renderDialog({ companyHolidays: [...lastYear, silvester] });

		await userEvent.click(
			within(dialog()).getByRole("button", { name: "Copy last year's company days" }),
		);

		expect(hooks.mutate).not.toHaveBeenCalled();
		expect(within(dialog()).getByRole("status")).toHaveTextContent(
			"Copied 2 days from 2025 — save to keep them. Left out: Dec 25, already a public holiday · Dec 31, already a company day.",
		);
		expect(within(dialog()).getByLabelText("Company holiday 2: date")).toHaveValue("2026-10-31");
		expect(within(dialog()).getByLabelText("Company holiday 2: name")).toHaveAccessibleDescription(
			"On a weekend — changes nothing",
		);
		expect(within(dialog()).getByLabelText("Company holiday 3: date")).toHaveValue("2026-12-24");
		expect(
			within(dialog()).getByLabelText("Company holiday 3: name"),
		).not.toHaveAccessibleDescription();

		await userEvent.click(within(dialog()).getByRole("button", { name: "Save" }));

		expect(sentContract().company_holidays).toEqual([
			...lastYear,
			silvester,
			{ date: "2026-10-31", name: "Bridge day" },
			{ date: "2026-12-24", name: "Christmas Eve" },
		]);
	});

	it("leaves out a copied day on a public holiday ticked back on, though saved as not given", async () => {
		hooks.holidays.mockImplementation((year: number) =>
			year === 2026 ? [holiday("2026-12-25", "Christmas Day", false)] : [],
		);
		renderDialog({
			companyHolidays: [{ date: "2025-12-25", name: "Firm Christmas" }],
			holidaysNotGiven: ["2026-12-25"],
		});

		await userEvent.click(within(dialog()).getByRole("checkbox", { name: /Christmas Day/ }));
		await userEvent.click(
			within(dialog()).getByRole("button", { name: "Copy last year's company days" }),
		);

		expect(within(dialog()).getByRole("status")).toHaveTextContent(
			"Nothing copied from 2025. Left out: Dec 25, already a public holiday.",
		);
	});

	it("copies a day on a public holiday just unticked, and names no public holiday on its row", async () => {
		renderDialog({ companyHolidays: [{ date: "2025-12-25", name: "Firm Christmas" }] });

		await userEvent.click(within(dialog()).getByRole("checkbox", { name: /Christmas Day/ }));
		await userEvent.click(
			within(dialog()).getByRole("button", { name: "Copy last year's company days" }),
		);

		expect(within(dialog()).getByRole("status")).toHaveTextContent(
			"Copied 1 day from 2025 — save to keep it.",
		);
		expect(within(dialog()).getByLabelText("Company holiday 1: date")).toHaveValue("2026-12-25");
		expect(
			within(dialog()).getByLabelText("Company holiday 1: name"),
		).not.toHaveAccessibleDescription();
	});

	it("drops the copy's line once a copied day is removed, there and on coming back", async () => {
		renderDialog({ companyHolidays: [{ date: "2025-12-24", name: "Christmas Eve" }] });

		await userEvent.click(
			within(dialog()).getByRole("button", { name: "Copy last year's company days" }),
		);
		await userEvent.click(
			within(dialog()).getByRole("button", { name: "Remove company holiday 1" }),
		);

		expect(within(dialog()).getByRole("status")).toBeEmptyDOMElement();
		await userEvent.click(within(dialog()).getByRole("button", { name: "Previous year" }));
		await userEvent.click(within(dialog()).getByRole("button", { name: "Next year" }));
		expect(within(dialog()).getByRole("status")).toBeEmptyDOMElement();
	});

	it("offers the copy only on a year whose year before has a company day", async () => {
		renderDialog({ companyHolidays: [{ date: "2026-12-24", name: "Christmas Eve" }] });
		const copy = { name: "Copy last year's company days" };

		expect(within(dialog()).queryByRole("button", copy)).not.toBeInTheDocument();

		await userEvent.click(within(dialog()).getByRole("button", { name: "Next year" }));
		await userEvent.click(within(dialog()).getByRole("button", copy));

		expect(within(dialog()).getByLabelText("Company holiday 1: date")).toHaveValue("2027-12-24");
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
