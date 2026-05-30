import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectIntentionStrip } from "./ProjectIntentionStrip";

const useIntentionsMock = vi.fn();
const useRecurringMock = vi.fn();
const updateMutate = vi.fn();

vi.mock("@/entities/planning", () => ({
	useIntentions: () => useIntentionsMock(),
	useRecurringIntentions: () => useRecurringMock(),
	useUpdateIntention: () => ({ mutate: updateMutate, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderStrip() {
	return render(
		<MemoryRouter>
			<ProjectIntentionStrip projectId="p1" projectName="Alpha" />
		</MemoryRouter>,
	);
}

describe("ProjectIntentionStrip", () => {
	beforeEach(() => {
		useIntentionsMock.mockReturnValue({ data: [] });
		useRecurringMock.mockReturnValue({ data: [] });
		updateMutate.mockReset();
	});
	afterEach(cleanup);

	it("shows a zero-state with Plan + recurring CTAs when nothing exists", () => {
		renderStrip();
		expect(screen.getByText("No intention set today.")).toBeInTheDocument();
		expect(screen.getByRole("link", { name: /Plan one/ })).toBeInTheDocument();
		expect(screen.getByRole("link", { name: /Set a recurring intention/ })).toBeInTheDocument();
	});

	it("renders today's intention with a completion checkbox", async () => {
		useIntentionsMock.mockReturnValue({
			data: [
				{
					id: "i1",
					project_id: "p1",
					date: "2026-05-30",
					planned_minutes: 90,
					completed: false,
				},
			],
		});
		renderStrip();

		const cb = screen.getByRole("checkbox", { name: /Mark Alpha intention complete/ });
		expect(cb).not.toBeChecked();

		await userEvent.click(cb);
		expect(updateMutate).toHaveBeenCalledWith(
			{ intentionId: "i1", updates: { completed: true } },
			expect.anything(),
		);
	});

	it("renders the recurring template + deep links to /plan", () => {
		useRecurringMock.mockReturnValue({
			data: [
				{
					id: "r1",
					project_id: "p1",
					planned_minutes: 60,
					days_of_week: [0, 1, 2, 3, 4],
					enabled: true,
				},
			],
		});
		renderStrip();

		expect(screen.getByText(/Recurring/i)).toBeInTheDocument();
		expect(screen.getByRole("link", { name: /Edit/ })).toHaveAttribute("href", "/plan");
	});

	it("ignores intentions/templates that belong to other projects", () => {
		useIntentionsMock.mockReturnValue({
			data: [
				{ id: "x", project_id: "other", date: "2026-05-30", planned_minutes: 45, completed: false },
			],
		});
		useRecurringMock.mockReturnValue({
			data: [
				{ id: "x", project_id: "other", planned_minutes: 30, days_of_week: [0], enabled: true },
			],
		});
		renderStrip();
		// Falls back to the empty state because no entries match projectId "p1".
		expect(screen.getByText("No intention set today.")).toBeInTheDocument();
	});
});
