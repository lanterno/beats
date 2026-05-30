import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectHealthRail } from "./ProjectHealthRail";

const useProjectHealthMock = vi.fn();
const useFocusScoresMock = vi.fn();
const dismissMutate = vi.fn();

vi.mock("@/entities/intelligence", () => ({
	useProjectHealth: () => useProjectHealthMock(),
	useFocusScores: () => useFocusScoresMock(),
	useDismissInboxItem: () => ({ mutate: dismissMutate, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("ProjectHealthRail", () => {
	beforeEach(() => {
		useProjectHealthMock.mockReturnValue({ data: undefined });
		useFocusScoresMock.mockReturnValue({ data: [] });
		dismissMutate.mockReset();
	});
	afterEach(cleanup);

	it("renders nothing until health data loads", () => {
		const { container } = render(<ProjectHealthRail projectId="p1" todaysProjectSessions={[]} />);
		expect(container).toBeEmptyDOMElement();
	});

	it("shows the all-clear message + recency when there's no alert", () => {
		useProjectHealthMock.mockReturnValue({
			data: [
				{
					project_id: "p1",
					project_name: "Alpha",
					days_since_last: 2,
					weekly_goal_trend: [3, 5, 8, 6],
					avg_session_length_trend: [],
					alert: null,
				},
			],
		});
		render(<ProjectHealthRail projectId="p1" todaysProjectSessions={[]} />);
		expect(screen.getByText(/All clear — last tracked 2 days ago/)).toBeInTheDocument();
	});

	it("surfaces the alert with a Snooze 7d button that dismisses the inbox item", async () => {
		useProjectHealthMock.mockReturnValue({
			data: [
				{
					project_id: "p1",
					project_name: "Alpha",
					days_since_last: 9,
					weekly_goal_trend: [],
					avg_session_length_trend: [],
					alert: "stale_project",
				},
			],
		});
		render(<ProjectHealthRail projectId="p1" todaysProjectSessions={[]} />);

		expect(screen.getByText(/quiet for a while/)).toBeInTheDocument();
		await userEvent.click(screen.getByRole("button", { name: /Snooze 7d/ }));
		expect(dismissMutate).toHaveBeenCalledWith("project_health:p1", expect.anything());
	});

	it("does nothing when health exists but not for this project", () => {
		useProjectHealthMock.mockReturnValue({
			data: [
				{
					project_id: "other",
					project_name: "Other",
					days_since_last: 1,
					weekly_goal_trend: [],
					avg_session_length_trend: [],
					alert: null,
				},
			],
		});
		const { container } = render(<ProjectHealthRail projectId="p1" todaysProjectSessions={[]} />);
		expect(container).toBeEmptyDOMElement();
	});
});
