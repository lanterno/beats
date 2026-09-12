import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Project } from "@/entities/project";
import { ContractHistoryPanel } from "./ContractHistoryPanel";

const mutate = vi.fn();

vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return { ...actual, useUpdateContract: () => ({ mutate, isPending: false }) };
});
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function dayJob(terms: NonNullable<Project["contract"]>["terms"]): Project {
	return {
		id: "p1",
		name: "Employer",
		color: "#888",
		archived: false,
		goalOverrides: [],
		autostartRepos: [],
		kind: "day_job",
		contract: { terms, holidayCountry: "CH", openingBalanceHours: 1.5 },
	};
}

const FULL_TIME = {
	effectiveFrom: "2026-01-05",
	scheduleType: "full_time" as const,
	fullTimeHours: 42,
	percentage: 1,
};
const PART_TIME = {
	effectiveFrom: "2026-04-01",
	scheduleType: "part_time" as const,
	fullTimeHours: 42,
	percentage: 0.8,
};

describe("ContractHistoryPanel", () => {
	beforeEach(() => mutate.mockReset());
	afterEach(cleanup);

	it("renders nothing for a project that is not a day job", () => {
		const { container } = render(
			<ContractHistoryPanel
				project={{ ...dayJob([FULL_TIME]), kind: "freelance", contract: undefined }}
				onOpenSettings={vi.fn()}
			/>,
		);
		expect(container).toBeEmptyDOMElement();
	});

	it("appends a term and PUTs the whole contract, in date order", async () => {
		render(
			<ContractHistoryPanel project={dayJob([FULL_TIME, PART_TIME])} onOpenSettings={vi.fn()} />,
		);

		await userEvent.click(screen.getByRole("button", { name: /Change contract from/ }));
		const dialog = screen.getByRole("dialog");
		fireEvent.change(within(dialog).getByLabelText("From"), { target: { value: "2026-03-01" } });
		await userEvent.click(within(dialog).getByRole("radio", { name: /Custom/ }));
		await userEvent.type(within(dialog).getByLabelText("Hours per week"), "20");
		await userEvent.click(within(dialog).getByRole("button", { name: "Save term" }));

		expect(mutate).toHaveBeenCalledTimes(1);
		const { projectId, contract } = mutate.mock.calls[0][0];
		expect(projectId).toBe("p1");
		// The frame rides along untouched; the new term lands between the two.
		expect(contract.holiday_country).toBe("CH");
		expect(contract.opening_balance_hours).toBe(1.5);
		expect(contract.terms.map((t: { effective_from: string }) => t.effective_from)).toEqual([
			"2026-01-05",
			"2026-03-01",
			"2026-04-01",
		]);
		expect(contract.terms[1]).toMatchObject({ schedule_type: "custom", weekly_hours: 20 });
	});

	it("refuses a second term on a day one already starts", async () => {
		render(
			<ContractHistoryPanel project={dayJob([FULL_TIME, PART_TIME])} onOpenSettings={vi.fn()} />,
		);

		await userEvent.click(screen.getByRole("button", { name: /Change contract from/ }));
		const dialog = screen.getByRole("dialog");
		fireEvent.change(within(dialog).getByLabelText("From"), { target: { value: "2026-04-01" } });
		await userEvent.click(within(dialog).getByRole("button", { name: "Save term" }));

		expect(mutate).not.toHaveBeenCalled();
		expect(within(dialog).getByLabelText("From")).toHaveAttribute("aria-invalid", "true");
	});

	it("removes a term but never the last one", async () => {
		const { unmount } = render(
			<ContractHistoryPanel project={dayJob([FULL_TIME, PART_TIME])} onOpenSettings={vi.fn()} />,
		);
		// Rows are in date order, so the first Remove is January's — read that
		// way rather than through the locale's month name.
		await userEvent.click(screen.getAllByRole("button", { name: /Remove term from/ })[0]);
		expect(mutate).toHaveBeenCalledTimes(1);
		expect(mutate.mock.calls[0][0].contract.terms).toHaveLength(1);
		expect(mutate.mock.calls[0][0].contract.terms[0].effective_from).toBe("2026-04-01");
		unmount();

		render(<ContractHistoryPanel project={dayJob([FULL_TIME])} onOpenSettings={vi.fn()} />);
		expect(screen.getByRole("button", { name: /Remove term/ })).toBeDisabled();
	});
});
