/**
 * A client whose only time this month is a timer still running: the month
 * leaves running time out until it stops (`running` on the client), and the
 * panel must say that rather than that nothing was logged — the sentence
 * above it says a timer is running for the same client.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ClientBilling } from "@/entities/billing";
import { ClientPanel } from "./ClientPanel";

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

function renderPanel(billing: ClientBilling) {
	render(
		<MemoryRouter>
			<ClientPanel
				billing={billing}
				todayIso="2026-10-17"
				tz="Europe/Berlin"
				monthName="October"
				projectNames={new Map()}
				onEdit={vi.fn()}
			/>
		</MemoryRouter>,
	);
}

afterEach(cleanup);

describe("ClientPanel", () => {
	it("says a running timer counts once stopped, not that nothing was logged", () => {
		renderPanel({ ...KITE, running: true });
		const panel = screen.getByRole("region", { name: "Studio Kite" });
		expect(panel).not.toHaveTextContent("Nothing logged");
		expect(panel).toHaveTextContent("a timer is running");
	});
});
