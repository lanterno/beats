/**
 * Settings is where a session that may have been someone else's is
 * answered, since a report link outlives the session that made it. It lists
 * only the links that still open, and Turn off all asks first and then
 * ends every client's at once: `client_id` null, not one client's.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReportLink } from "@/entities/report-link";

const { state } = vi.hoisted(() => ({
	state: {
		links: [] as unknown[],
		turnOffAll: vi.fn(),
		deleteLink: vi.fn(),
	},
}));

vi.mock("@/entities/report-link", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/report-link")>("@/entities/report-link");
	return {
		...actual,
		useReportLinks: () => ({ data: state.links, isError: false }),
		useDeleteReportLink: () => ({ isPending: false, mutate: state.deleteLink }),
		useTurnOffReportLinks: () => ({ isPending: false, mutate: state.turnOffAll }),
	};
});
vi.mock("@/entities/client", async () => {
	const actual = await vi.importActual<typeof import("@/entities/client")>("@/entities/client");
	return {
		...actual,
		useClients: ({ archived = false }: { archived?: boolean } = {}) => ({
			data: archived ? [] : [{ id: "c1", name: "Studio Kite" }],
		}),
	};
});

import { ReportLinksSection } from "./ReportLinksSection";

const LIVE: ReportLink = {
	id: "l1",
	clientId: "c1",
	label: "September",
	first: "2026-09-01",
	last: "2026-09-30",
	tz: "Europe/Berlin",
	showAmounts: false,
	showNotes: false,
	projects: [{ id: "p1", name: "Website" }],
	expiresOn: "2027-01-30",
	createdAt: "2026-10-02T10:00:00Z",
	state: "live",
};

function renderSection() {
	render(
		<MemoryRouter>
			<ReportLinksSection />
		</MemoryRouter>,
	);
	return screen.getByRole("region", { name: "Report links" });
}

beforeEach(() => {
	vi.clearAllMocks();
	state.links = [];
});
afterEach(cleanup);

describe("Settings' ReportLinksSection", () => {
	it("lists only live links", () => {
		state.links = [LIVE, { ...LIVE, id: "l2", label: "August", state: "ended" }];
		const section = renderSection();
		expect(within(section).getAllByRole("listitem")).toHaveLength(1);
		expect(section).toHaveTextContent("September");
		expect(section).toHaveTextContent("Studio Kite");
		expect(section).not.toHaveTextContent("August");
	});

	it("Turn off all confirms and sends null", async () => {
		state.links = [LIVE, { ...LIVE, id: "l2", clientId: "c2" }];
		const section = renderSection();

		const turnOffAll = within(section).getByRole("button", { name: "Turn off all report links" });
		await userEvent.click(turnOffAll);
		expect(await screen.findByText(/All 2 links, for every client/)).toBeVisible();
		await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
		expect(state.turnOffAll).not.toHaveBeenCalled();

		await userEvent.click(turnOffAll);
		await userEvent.click(await screen.findByRole("button", { name: "Turn off all" }));
		expect(state.turnOffAll).toHaveBeenCalledWith(null, expect.anything());
	});

	it("offers nothing to turn off when no link is live", () => {
		state.links = [{ ...LIVE, state: "ended" }];
		const section = renderSection();
		expect(section).toHaveTextContent("No report link is working right now.");
		expect(within(section).queryByRole("button", { name: /Turn off/ })).toBeNull();
	});
});
