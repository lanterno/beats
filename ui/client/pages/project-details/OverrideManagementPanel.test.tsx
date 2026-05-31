import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Project } from "@/entities/project";
import { OverrideManagementPanel } from "./OverrideManagementPanel";

const mutate = vi.fn();

vi.mock("@/entities/project", () => ({
	useUpdateGoalOverrides: () => ({
		mutate,
		isPending: false,
		variables: undefined,
	}),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function project(overrides: Project["goalOverrides"]): Project {
	return {
		id: "p1",
		name: "Alpha",
		color: "#888",
		archived: false,
		autostartRepos: [],
		goalOverrides: overrides,
	} as Project;
}

describe("OverrideManagementPanel", () => {
	beforeEach(() => mutate.mockReset());
	afterEach(cleanup);

	it("shows a friendly zero-state when there are no overrides", () => {
		render(<OverrideManagementPanel project={project([])} />);
		expect(screen.getByText(/No overrides yet/)).toBeInTheDocument();
	});

	it("lists each override with its scope, date, and goal", () => {
		render(
			<OverrideManagementPanel
				project={project([
					{ weekOf: "2026-05-25", weeklyGoal: 12, goalType: "target" },
					{ effectiveFrom: "2026-04-06", weeklyGoal: null, goalType: "cap" },
				])}
			/>,
		);
		// Each row carries a Remove button labelled with the date so SR users
		// know which override they're removing.
		expect(screen.getAllByRole("button", { name: /Remove override/ })).toHaveLength(2);
		expect(screen.getByText("12h target")).toBeInTheDocument();
		expect(screen.getByText("No goal")).toBeInTheDocument();
	});

	it("removes an override by mutating with the residual list", async () => {
		render(
			<OverrideManagementPanel
				project={project([
					{ weekOf: "2026-05-25", weeklyGoal: 12, goalType: "target" },
					{ weekOf: "2026-04-20", weeklyGoal: 8, goalType: "target" },
				])}
			/>,
		);

		// The 25 May row is listed first (sorted by date desc).
		const buttons = screen.getAllByRole("button", { name: /Remove override/ });
		await userEvent.click(buttons[0]);

		expect(mutate).toHaveBeenCalledTimes(1);
		const [args] = mutate.mock.calls;
		expect(args[0].projectId).toBe("p1");
		expect(args[0].overrides).toHaveLength(1);
		expect(args[0].overrides[0].week_of).toBe("2026-04-20");
	});

	it("FF.6: deleting one of two overrides sharing the same scope removes only the clicked row", async () => {
		// Two overrides for the same Monday (legacy cleanup territory per
		// the panel header). The pre-FF.6 implementation filtered by the
		// composite (weekOf, effectiveFrom) key and nuked both. Identity-
		// based filtering keeps the other one in place.
		render(
			<OverrideManagementPanel
				project={project([
					{ weekOf: "2026-05-25", weeklyGoal: 12, goalType: "target" },
					{ weekOf: "2026-05-25", weeklyGoal: 8, goalType: "cap" },
				])}
			/>,
		);

		// Both rows render. Both labelled identically (same date), so query
		// by all and click the second.
		const buttons = screen.getAllByRole("button", { name: /Remove override/ });
		expect(buttons).toHaveLength(2);
		await userEvent.click(buttons[1]);

		expect(mutate).toHaveBeenCalledTimes(1);
		const [args] = mutate.mock.calls;
		expect(args[0].overrides).toHaveLength(1);
		// The surviving override is the one we did NOT click. The sort is
		// week-desc-then-input order, but with equal weekOf the input order
		// is preserved — index 1 (in sorted) maps back to overrides[1]
		// (the cap), so the survivor is the target (weeklyGoal=12).
		expect(args[0].overrides[0].weekly_goal).toBe(12);
		expect(args[0].overrides[0].goal_type).toBe("target");
	});
});
