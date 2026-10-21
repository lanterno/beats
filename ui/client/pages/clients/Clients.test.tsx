/**
 * The Clients page's states that depend on what the account holds: with no
 * client yet, the freelance hours billed to no one are still shown, with a
 * way to bill them — the state a first freelance project is in, which the
 * sidebar already offers the page for. And when the month cannot be read —
 * an older API during a deploy answers 404 "Not Found" — the page's own
 * sentence and the API's words stay apart. An archived client with no panel
 * in the month still has its report links on the page.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BillingBudgetStatus, BillingMonth, ClientBilling } from "@/entities/billing";
import type { Client } from "@/entities/client";
import type { ReportLink } from "@/entities/report-link";
import { ApiError } from "@/shared/api";
import Clients from "./Clients";

const { state, idle } = vi.hoisted(() => ({
	state: {
		month: { data: undefined, error: null } as { data?: unknown; error: unknown },
		budgets: { data: [], isError: false } as { data: unknown[]; isError: boolean },
		archived: [] as Client[],
		links: [] as ReportLink[],
	},
	// A mutation nothing here sends.
	idle: () => ({ isPending: false, mutate: vi.fn(), mutateAsync: vi.fn() }),
}));

vi.mock("@/entities/billing", async () => {
	const actual = await vi.importActual<typeof import("@/entities/billing")>("@/entities/billing");
	return {
		...actual,
		useBillingMonth: () => state.month,
		useBillingBudgets: () => state.budgets,
		useProjectBillings: () => ({ data: new Map() }),
		useBillableOverrides: () => ({ data: new Map() }),
	};
});
vi.mock("@/entities/client", async () => {
	const actual = await vi.importActual<typeof import("@/entities/client")>("@/entities/client");
	return {
		...actual,
		useClients: ({ archived = false }: { archived?: boolean } = {}) => ({
			data: archived ? state.archived : [],
			isLoading: false,
		}),
		useCreateClient: idle,
		useUpdateClient: idle,
		useUnarchiveClient: idle,
		useArchiveClient: idle,
		useDeleteClient: idle,
	};
});
vi.mock("@/entities/report-link", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/report-link")>("@/entities/report-link");
	return {
		...actual,
		useReportLinks: () => ({ data: state.links, isError: false }),
		useDeleteReportLink: idle,
	};
});
vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return {
		...actual,
		useProjects: () => ({ data: [] }),
		useArchivedProjects: () => ({ data: [] }),
	};
});

function month(fields: Partial<BillingMonth> = {}): BillingMonth {
	return {
		month: "2026-10",
		first: "2026-10-01",
		last: "2026-10-17",
		totals: [],
		clients: [],
		unattached: [],
		...fields,
	};
}

function renderPage() {
	render(
		<MemoryRouter initialEntries={["/clients"]}>
			<Clients />
		</MemoryRouter>,
	);
}

beforeEach(() => {
	state.month = { data: month(), error: null };
	state.budgets = { data: [], isError: false };
	state.archived = [];
	state.links = [];
});
afterEach(cleanup);

const KITE: ClientBilling = {
	clientId: "c1",
	name: "Studio Kite",
	archived: false,
	currency: "EUR",
	minorUnits: 2,
	running: false,
	billableHours: 42,
	nonBillableHours: 0,
	unpricedHours: 0,
	amountMinor: 357_000,
	lines: [],
	entries: [],
};

const KITE_USED_UP: BillingBudgetStatus = {
	scope: "client",
	scopeId: "c1",
	clientId: "c1",
	name: "Studio Kite",
	active: true,
	currency: "EUR",
	minorUnits: 2,
	unit: "hours",
	period: "monthly",
	limitHours: 40,
	warnAtPercent: 80,
	upcoming: false,
	first: "2026-10-01",
	last: "2026-10-31",
	through: "2026-10-17",
	billableHours: 42,
	unpricedHours: 0,
	amountMinor: 357_000,
	remainingHours: -2,
	percentUsed: 105,
	state: "used_up",
};

describe("Clients", () => {
	it("with no client yet, still shows the freelance hours billed to no one", () => {
		state.month = {
			data: month({ unattached: [{ projectId: "p1", name: "Logo refresh", hours: 4 }] }),
			error: null,
		};
		renderPage();

		expect(screen.getByText("Clients are who you bill.")).toBeInTheDocument();
		const unbilled = screen.getByRole("region", { name: "Not billed to a client" });
		expect(unbilled).toHaveTextContent("Logo refresh");
		expect(within(unbilled).getByRole("link", { name: "Bill it" })).toHaveAttribute(
			"href",
			"/project/p1",
		);
	});

	it("keeps the API's words apart from its own when the month cannot be read", () => {
		state.month = { data: undefined, error: new ApiError(404, "Not Found") };
		renderPage();

		const failure = screen.getByRole("alert");
		expect(within(failure).getByText("The rest of the site works as usual.")).toBeInTheDocument();
		expect(within(failure).getByText("Not Found")).toBeInTheDocument();
	});

	it("when the budgets cannot be read, says so and keeps no note from a reading before", () => {
		// TanStack keeps the last good data beside a failed refetch's error.
		state.month = { data: month({ clients: [KITE] }), error: null };
		state.budgets = { data: [KITE_USED_UP], isError: true };
		renderPage();

		const panel = screen.getByRole("region", { name: "Studio Kite" });
		expect(panel).toHaveTextContent("Budgets aren't available right now.");
		expect(screen.getByRole("region", { name: "Summary" })).not.toHaveTextContent("budget");
	});

	it("lists an archived client's report links in a month it has no panel in", async () => {
		state.archived = [
			{
				id: "c9",
				name: "Kite Archive",
				currency: "EUR",
				minorUnits: 2,
				rates: [],
				archived: true,
				createdAt: "2026-01-02T10:00:00Z",
				currencyLocked: false,
			},
		];
		const link: ReportLink = {
			id: "l1",
			clientId: "c9",
			label: "Spring",
			first: "2026-03-01",
			last: "2026-03-31",
			tz: "Europe/Berlin",
			showAmounts: false,
			showNotes: false,
			projects: [],
			expiresOn: "2026-12-31",
			createdAt: "2026-04-02T10:00:00Z",
			state: "live",
		};
		state.links = [link, { ...link, id: "l2", label: "Winter", state: "ended" }];
		renderPage();

		await userEvent.click(screen.getByRole("button", { name: "Archived clients (1)" }));
		const section = screen.getByRole("region", { name: "Kite Archive's report links" });
		await userEvent.click(within(section).getByRole("button", { name: "Report links (2)" }));

		expect(within(section).getByText("Spring")).toBeInTheDocument();
		expect(within(section).getByText("Winter")).toBeInTheDocument();
		expect(within(section).getByRole("button", { name: "Turn off" })).toBeInTheDocument();
		expect(within(section).getByRole("button", { name: "Remove" })).toBeInTheDocument();
	});
});
