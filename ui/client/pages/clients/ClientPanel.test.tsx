/**
 * A client whose only time this month is a timer still running: the month
 * leaves running time out until it stops (`running` on the client), and the
 * panel must say that rather than that nothing was logged — the sentence
 * above it says a timer is running for the same client.
 *
 * And its billing budgets in the current month: a row for each, sentence
 * and meter, a quiet "Set a budget" while the client has none of its own,
 * nothing at all in a month already over, and a line of its own when the
 * budgets cannot be read.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BillingBudgetStatus, ClientBilling } from "@/entities/billing";
import { ClientPanel, type ClientPanelProps } from "./ClientPanel";

const { idle } = vi.hoisted(() => ({
	// A mutation nothing here sends.
	idle: () => ({ isPending: false, mutate: vi.fn() }),
}));

vi.mock("@/entities/client", async () => {
	const actual = await vi.importActual<typeof import("@/entities/client")>("@/entities/client");
	return {
		...actual,
		useArchiveClient: idle,
		useUnarchiveClient: idle,
		useDeleteClient: idle,
	};
});

const KITE: ClientBilling = {
	clientId: "c1",
	name: "Studio Kite",
	archived: false,
	currency: "EUR",
	minorUnits: 2,
	running: false,
	billableHours: 0,
	nonBillableHours: 0,
	unpricedHours: 0,
	amountMinor: 0,
	lines: [],
	entries: [],
};

function renderPanel(billing: ClientBilling, props: Partial<ClientPanelProps> = {}) {
	render(
		<MemoryRouter>
			<ClientPanel
				billing={billing}
				todayIso="2026-10-17"
				tz="Europe/Berlin"
				monthName="October"
				projectNames={new Map()}
				onEdit={vi.fn()}
				{...props}
			/>
		</MemoryRouter>,
	);
	return screen.getByRole("region", { name: billing.name });
}

const WEBSITE_BUDGET: BillingBudgetStatus = {
	scope: "project",
	scopeId: "p1",
	clientId: "c1",
	name: "Website",
	active: true,
	currency: "EUR",
	minorUnits: 2,
	unit: "money",
	period: "total",
	limitMinor: 1_020_000,
	startsOn: "2026-09-01",
	warnAtPercent: 80,
	upcoming: false,
	first: "2026-09-01",
	through: "2026-10-17",
	billableHours: 84,
	unpricedHours: 0,
	amountMinor: 684_250,
	remainingMinor: 335_750,
	percentUsed: 67,
	state: "under",
};

afterEach(cleanup);

describe("ClientPanel", () => {
	it("says a running timer counts once stopped, not that nothing was logged", () => {
		renderPanel({ ...KITE, running: true });
		const panel = screen.getByRole("region", { name: "Studio Kite" });
		expect(panel).not.toHaveTextContent("Nothing logged");
		expect(panel).toHaveTextContent("a timer is running");
	});

	it("draws each budget's row, and offers one for the client while it has none", () => {
		const panel = renderPanel(KITE, { budgets: [WEBSITE_BUDGET], now: Date.now() });
		const block = within(panel).getByRole("region", { name: "Studio Kite's budgets" });
		expect(block).toHaveTextContent("€6,842.50 of €10,200.00 since Sep 1 · €3,357.50 left.");
		expect(within(block).getByRole("meter", { name: "Website's budget" })).toHaveAttribute(
			"aria-valuenow",
			"67",
		);
		expect(within(block).getByRole("button", { name: "Edit Website's budget" })).toBeVisible();
		expect(
			within(block).getByRole("button", { name: "Set a budget for Studio Kite" }),
		).toBeVisible();
	});

	it("offers a budget and nothing more when there is none", () => {
		const panel = renderPanel(KITE, { budgets: [] });
		expect(within(panel).getByRole("button", { name: "Set a budget" })).toBeVisible();
		expect(within(panel).queryByRole("region", { name: "Studio Kite's budgets" })).toBeNull();
	});

	it("shows no budget in a month already over", () => {
		const panel = renderPanel(KITE);
		expect(within(panel).queryByRole("button", { name: /Set a budget/ })).toBeNull();
		expect(within(panel).queryByRole("meter")).toBeNull();
	});

	it("says the budgets cannot be read, and draws the month as before", () => {
		const panel = renderPanel(KITE, { budgetsFailed: true });
		expect(panel).toHaveTextContent("Budgets aren't available right now.");
		expect(panel).toHaveTextContent("Nothing logged for Studio Kite in October.");
		expect(within(panel).queryByRole("button", { name: /Set a budget/ })).toBeNull();
	});

	it("on an archived client, shows its budgets and offers no write", () => {
		const archived = { ...KITE, archived: true };
		const own: BillingBudgetStatus = {
			...WEBSITE_BUDGET,
			scope: "client",
			scopeId: "c1",
			name: "Studio Kite",
			active: false,
		};
		const panel = renderPanel(archived, {
			budgets: [own, { ...WEBSITE_BUDGET, active: false }],
			now: Date.now(),
		});
		expect(within(panel).getAllByRole("meter")).toHaveLength(2);
		expect(within(panel).queryByRole("button", { name: /budget/ })).toBeNull();
		cleanup();

		const none = renderPanel(archived, { budgets: [] });
		expect(within(none).queryByRole("button", { name: /budget/ })).toBeNull();
	});

	it("gives focus to the client's budget control when a save or a remove took the opener away", async () => {
		// The first budget's save takes "Set a budget" off the page, and
		// the billing root's refetch lands before the dialog closes.
		const own: BillingBudgetStatus = {
			...WEBSITE_BUDGET,
			scope: "client",
			scopeId: "c1",
			name: "Studio Kite",
		};
		const panel = (budgets: BillingBudgetStatus[]) => (
			<QueryClientProvider client={new QueryClient()}>
				<MemoryRouter>
					<ClientPanel
						billing={KITE}
						todayIso="2026-10-17"
						tz="Europe/Berlin"
						monthName="October"
						projectNames={new Map()}
						budgets={budgets}
						now={Date.now()}
						onEdit={vi.fn()}
					/>
				</MemoryRouter>
			</QueryClientProvider>
		);
		const { rerender } = render(panel([]));

		await userEvent.click(screen.getByRole("button", { name: "Set a budget" }));
		expect(screen.getByRole("dialog")).toBeInTheDocument();
		rerender(panel([own]));
		await userEvent.keyboard("{Escape}");
		await waitFor(() =>
			expect(screen.getByRole("button", { name: "Edit Studio Kite's budget" })).toHaveFocus(),
		);

		await userEvent.click(screen.getByRole("button", { name: "Edit Studio Kite's budget" }));
		rerender(panel([]));
		await userEvent.keyboard("{Escape}");
		await waitFor(() => expect(screen.getByRole("button", { name: "Set a budget" })).toHaveFocus());
	});
});
