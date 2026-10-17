/**
 * The Clients page's states that depend on what the account holds: with no
 * client yet, the freelance hours billed to no one are still shown, with a
 * way to bill them — the state a first freelance project is in, which the
 * sidebar already offers the page for.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BillingMonth } from "@/entities/billing";
import Clients from "./Clients";

const { state, idle } = vi.hoisted(() => ({
	state: { month: { data: undefined, error: null } as { data?: unknown; error: unknown } },
	// A mutation nothing here sends.
	idle: () => ({ isPending: false, mutate: vi.fn(), mutateAsync: vi.fn() }),
}));

vi.mock("@/entities/billing", async () => {
	const actual = await vi.importActual<typeof import("@/entities/billing")>("@/entities/billing");
	return {
		...actual,
		useBillingMonth: () => state.month,
		useProjectBillings: () => ({ data: new Map() }),
		useBillableOverrides: () => ({ data: new Map() }),
	};
});
vi.mock("@/entities/client", async () => {
	const actual = await vi.importActual<typeof import("@/entities/client")>("@/entities/client");
	return {
		...actual,
		useClients: () => ({ data: [], isLoading: false }),
		useCreateClient: idle,
		useUpdateClient: idle,
		useUnarchiveClient: idle,
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
});
afterEach(cleanup);

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
});
