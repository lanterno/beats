import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RecurringIntentions } from "./RecurringIntentions";

const createMutate = vi.fn();
const deleteMutate = vi.fn();
const applyMutate = vi.fn();
const useRecurringMock = vi.fn();

vi.mock("@/entities/planning", () => ({
	useRecurringIntentions: () => useRecurringMock(),
	useCreateRecurringIntention: () => ({ mutate: createMutate, isPending: false }),
	useDeleteRecurringIntention: () => ({ mutate: deleteMutate, isPending: false }),
	useApplyRecurring: () => ({ mutate: applyMutate, isPending: false }),
}));

vi.mock("@/entities/project", () => ({
	useProjects: () => ({
		data: [
			{ id: "p1", name: "Alpha", color: "#f00", archived: false },
			{ id: "p2", name: "Beta", color: "#0f0", archived: false },
		],
	}),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("RecurringIntentions", () => {
	beforeEach(() => {
		createMutate.mockReset();
		deleteMutate.mockReset();
		applyMutate.mockReset();
		useRecurringMock.mockReset();
		useRecurringMock.mockReturnValue({
			data: [
				{ id: "r1", project_id: "p1", planned_minutes: 90, days_of_week: [0, 2, 4], enabled: true },
			],
		});
	});

	afterEach(cleanup);

	it("lists an existing template with project name and hours", () => {
		render(<RecurringIntentions />);
		// "Alpha" also appears as a <select> option, so target the row via its
		// unique delete control plus the (unique) hours label.
		expect(
			screen.getByRole("button", { name: "Delete recurring intention for Alpha" }),
		).toBeInTheDocument();
		expect(screen.getByText("1.5h")).toBeInTheDocument();
	});

	it("applies recurring intentions to today", async () => {
		render(<RecurringIntentions />);
		await userEvent.click(screen.getByRole("button", { name: /Apply to today/ }));
		expect(applyMutate).toHaveBeenCalledTimes(1);
	});

	it("disables Apply when there are no templates", () => {
		useRecurringMock.mockReturnValue({ data: [] });
		render(<RecurringIntentions />);
		expect(screen.getByRole("button", { name: /Apply to today/ })).toBeDisabled();
	});

	it("creates a template from the form with the default weekday set", async () => {
		render(<RecurringIntentions />);
		await userEvent.selectOptions(screen.getByLabelText("Project"), "p2");
		await userEvent.click(screen.getByRole("button", { name: "Add" }));

		// Default 1h, default Mon–Fri (0–4).
		expect(createMutate).toHaveBeenCalledWith(
			{ project_id: "p2", planned_minutes: 60, days_of_week: [0, 1, 2, 3, 4] },
			expect.anything(),
		);
	});

	it("deletes a template by id", async () => {
		render(<RecurringIntentions />);
		await userEvent.click(
			screen.getByRole("button", { name: "Delete recurring intention for Alpha" }),
		);
		expect(deleteMutate).toHaveBeenCalledWith("r1", expect.anything());
	});
});
