/**
 * Stopping billing on a project with a billing budget: the API refuses
 * unless `remove_billing_budget` is true, and the budget goes with the
 * billing when it is. So the confirmation names the budget, and only that
 * confirmation sends true; without a budget it sends false, as a tab that
 * never saw one would.
 */
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BillingBudgetStatus, ProjectBilling } from "@/entities/billing";
import type { ProjectWithDuration } from "@/entities/project";
import { BillingPanel } from "./BillingPanel";

const { hooks } = vi.hoisted(() => ({
	hooks: {
		removeBilling: vi.fn(),
		budgets: [] as unknown[],
	},
}));

vi.mock("@/entities/billing", async () => {
	const actual = await vi.importActual<typeof import("@/entities/billing")>("@/entities/billing");
	const idle = () => ({ isPending: false, mutate: vi.fn(), mutateAsync: vi.fn() });
	return {
		...actual,
		useBillingMonth: () => ({ data: undefined }),
		useBillingBudgets: () => ({ data: hooks.budgets, isError: false }),
		useSetProjectBilling: idle,
		useRemoveBillingBudget: idle,
		useRemoveProjectBilling: () => ({ isPending: false, mutateAsync: hooks.removeBilling }),
	};
});
vi.mock("@/entities/client", async () => {
	const actual = await vi.importActual<typeof import("@/entities/client")>("@/entities/client");
	return { ...actual, useClients: () => ({ data: [] }) };
});
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const PROJECT = { id: "p1", name: "Website", kind: "freelance" } as ProjectWithDuration;

const BILLING: ProjectBilling = {
	projectId: "p1",
	clientId: "c1",
	currency: "EUR",
	minorUnits: 2,
	terms: [{ effectiveFrom: "2026-10-01", billable: true }],
};

const BUDGET: BillingBudgetStatus = {
	scope: "project",
	scopeId: "p1",
	clientId: "c1",
	name: "Website",
	active: true,
	currency: "EUR",
	minorUnits: 2,
	unit: "hours",
	period: "total",
	limitHours: 120,
	startsOn: "2026-10-01",
	warnAtPercent: 80,
	upcoming: false,
	first: "2026-10-01",
	through: "2026-10-18",
	billableHours: 30,
	unpricedHours: 0,
	amountMinor: 0,
	remainingHours: 90,
	percentUsed: 25,
	state: "under",
};

async function stopBilling() {
	render(
		<MemoryRouter>
			<BillingPanel
				project={PROJECT}
				todayIso="2026-10-18"
				billing={BILLING}
				loading={false}
				error={null}
			/>
		</MemoryRouter>,
	);
	const panel = screen.getByRole("region", { name: "Billing" });
	await userEvent.click(within(panel).getByRole("button", { name: "Stop billing" }));
	return panel;
}

beforeEach(() => {
	hooks.removeBilling.mockReset();
	hooks.removeBilling.mockResolvedValue(undefined);
	hooks.budgets = [];
});
afterEach(cleanup);

describe("BillingPanel's Stop billing", () => {
	it("names the budget, and removes it with the billing", async () => {
		hooks.budgets = [BUDGET];
		const panel = await stopBilling();
		expect(panel).toHaveTextContent(
			"Stop billing Website? Its terms and its budget go; its hours stay.",
		);
		await userEvent.click(within(panel).getByRole("button", { name: "Stop billing" }));
		await waitFor(() =>
			expect(hooks.removeBilling).toHaveBeenCalledWith({
				projectId: "p1",
				rewritePast: false,
				removeBillingBudget: true,
			}),
		);
	});

	it("without a budget, names none and removes none", async () => {
		const panel = await stopBilling();
		expect(panel).toHaveTextContent("Stop billing Website? Its terms go; its hours stay.");
		await userEvent.click(within(panel).getByRole("button", { name: "Stop billing" }));
		await waitFor(() =>
			expect(hooks.removeBilling).toHaveBeenCalledWith({
				projectId: "p1",
				rewritePast: false,
				removeBillingBudget: false,
			}),
		);
	});
});
