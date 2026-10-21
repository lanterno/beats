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
 *
 * And its report links: an ended one says so and is only removed; a live
 * one is turned off after a question; the billed projects a link leaves
 * out are named under it; and when the links cannot be read the panel says
 * so and offers no Share.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BillingBudgetStatus, ClientBilling, ProjectBilling } from "@/entities/billing";
import type { ReportLink } from "@/entities/report-link";
import { ClientPanel, type ClientPanelProps } from "./ClientPanel";

const { idle, deleteLink } = vi.hoisted(() => ({
	// A mutation nothing here sends.
	idle: () => ({ isPending: false, mutate: vi.fn() }),
	deleteLink: vi.fn(),
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

vi.mock("@/entities/report-link", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/report-link")>("@/entities/report-link");
	return { ...actual, useDeleteReportLink: () => ({ isPending: false, mutate: deleteLink }) };
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

	describe("report links", () => {
		const billed = (projectId: string): [string, ProjectBilling] => [
			projectId,
			{ projectId, clientId: "c1", currency: "EUR", minorUnits: 2, terms: [] },
		];
		const links = {
			projectBillings: new Map([billed("p1"), billed("p2")]),
			projectNames: new Map([
				["p1", "Website"],
				["p2", "Logo"],
			]),
		};
		const LIVE: ReportLink = {
			id: "l1",
			clientId: "c1",
			label: "September",
			first: "2026-09-01",
			last: "2026-09-30",
			tz: "Europe/Berlin",
			showAmounts: true,
			showNotes: false,
			projects: [{ id: "p1", name: "Website" }],
			expiresOn: "2027-01-30",
			createdAt: "2026-10-02T10:00:00Z",
			state: "live",
		};

		async function openLinks(reportLinks: ReportLink[]) {
			const panel = renderPanel(KITE, { ...links, reportLinks });
			await userEvent.click(within(panel).getByRole("button", { name: /Report links/ }));
			return within(panel).getByRole("region", { name: "Studio Kite's report links" });
		}

		it("an ended link reads Ended and offers Remove", async () => {
			const section = await openLinks([{ ...LIVE, state: "ended" }]);
			expect(section).toHaveTextContent("Ended");
			expect(section).not.toHaveTextContent("Works until");
			expect(within(section).queryByRole("button", { name: "Turn off" })).toBeNull();

			await userEvent.click(within(section).getByRole("button", { name: "Remove" }));
			expect(deleteLink).toHaveBeenCalledWith("l1", expect.anything());
		});

		it("Not on this link names the billed project the link leaves out", async () => {
			const section = await openLinks([LIVE]);
			expect(section).toHaveTextContent("Not on this link: Logo");
			expect(section).toHaveTextContent("Works until 30 Jan 2027");
			expect(section).toHaveTextContent("1 Sep – 30 Sep 2026 · Hours and amounts · Website");
		});

		it("Turn off confirms, then deletes", async () => {
			const section = await openLinks([LIVE]);
			await userEvent.click(within(section).getByRole("button", { name: "Turn off" }));
			expect(await screen.findByText(/It can't be turned back on/)).toBeVisible();
			expect(deleteLink).not.toHaveBeenCalled();

			await userEvent.click(screen.getByRole("button", { name: "Turn off" }));
			expect(deleteLink).toHaveBeenCalledWith("l1", expect.anything());
		});

		it("the section says report links aren't available when the read fails", () => {
			const panel = renderPanel(KITE, { ...links, reportLinksFailed: true });
			expect(panel).toHaveTextContent("Report links aren't available right now.");
			expect(within(panel).queryByRole("button", { name: "Share" })).toBeNull();
			expect(panel).toHaveTextContent("Nothing logged for Studio Kite in October.");
			cleanup();

			const working = renderPanel(KITE, { ...links, reportLinks: [] });
			expect(within(working).getByRole("button", { name: "Share" })).toBeVisible();
		});
	});
});
