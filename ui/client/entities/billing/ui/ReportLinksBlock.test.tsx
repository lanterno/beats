/**
 * The owner's side of report links (docs/billing.md, phase 1c).
 *
 * Two things here are decisions rather than markup, and both would fail
 * quietly if they regressed: the disclosure reads nothing until it is
 * opened — the Clients page draws a panel per client, so an eager read is
 * a request per client — and Copy puts the SPA's own origin on the
 * clipboard, because the API returns a bare token and knows no origin.
 *
 * The hooks are mocked: they are thin wrappers over the API functions,
 * whose contract is covered by `TestReportLinksAPI` against a real
 * database.
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReportLink } from "../model";
import { describeReportLink, ReportLinksBlock } from "./ReportLinksBlock";

const { state, created, removed } = vi.hoisted(() => ({
	state: { links: { data: undefined, isError: false } as Record<string, unknown> },
	created: vi.fn(),
	removed: vi.fn(),
}));

vi.mock("../api", () => ({
	useReportLinks: (_clientId: string, options?: { enabled?: boolean }) =>
		options?.enabled === false ? { data: undefined, isError: false } : state.links,
	useCreateReportLink: () => ({ isPending: false, mutate: created }),
	useDeleteReportLink: () => ({ isPending: false, mutate: removed }),
}));

const OCTOBER: ReportLink = {
	id: "l1",
	clientId: "c1",
	token: "tok-october",
	first: "2026-10-01",
	last: "2026-10-31",
	tz: "Europe/Berlin",
	showAmounts: true,
	showEntries: true,
	createdAt: "2026-10-17T09:00:00Z",
};

function renderBlock(props: Partial<React.ComponentProps<typeof ReportLinksBlock>> = {}) {
	render(
		<ReportLinksBlock
			clientId="c1"
			clientName="Studio Kite"
			first="2026-10-01"
			last="2026-10-31"
			tz="Europe/Berlin"
			monthName="October"
			{...props}
		/>,
	);
}

afterEach(() => {
	cleanup();
	state.links = { data: undefined, isError: false };
	created.mockReset();
	removed.mockReset();
});

describe("ReportLinksBlock", () => {
	it("reads nothing until it is opened", async () => {
		state.links = { data: [OCTOBER], isError: false };
		renderBlock();

		// Closed: the hook is called with enabled false, so no link is drawn.
		expect(screen.queryByText("Oct 1 – Oct 31")).not.toBeInTheDocument();

		await userEvent.click(screen.getByRole("button", { name: /shared reports/i }));

		expect(screen.getByText("Oct 1 – Oct 31")).toBeInTheDocument();
	});

	it("copies the app's own origin with the token, not a bare token", async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
		state.links = { data: [OCTOBER], isError: false };
		renderBlock();
		await userEvent.click(screen.getByRole("button", { name: /shared reports/i }));

		await userEvent.click(screen.getByRole("button", { name: /^Copy/ }));

		expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/r/tok-october`);
		vi.unstubAllGlobals();
	});

	it("mints a link over the open month with the flags as set", async () => {
		state.links = { data: [], isError: false };
		renderBlock();
		await userEvent.click(screen.getByRole("button", { name: /shared reports/i }));

		await userEvent.click(screen.getByRole("button", { name: "Share October" }));
		await userEvent.click(screen.getByLabelText("Show rates and amounts"));
		await userEvent.click(screen.getByRole("button", { name: "Create link" }));

		expect(created).toHaveBeenCalledWith(
			{
				clientId: "c1",
				input: {
					first: "2026-10-01",
					last: "2026-10-31",
					tz: "Europe/Berlin",
					showAmounts: false,
					showEntries: true,
				},
			},
			expect.anything(),
		);
	});

	it("offers no way to make or revoke a link on an archived client", async () => {
		state.links = { data: [OCTOBER], isError: false };
		renderBlock({ writable: false });
		await userEvent.click(screen.getByRole("button", { name: /shared reports/i }));

		// The links it already has are still listed and still copyable: the
		// client holding one did not stop needing it.
		expect(screen.getByText("Oct 1 – Oct 31")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: /^Copy/ })).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "Share October" })).not.toBeInTheDocument();
	});

	it("says so when the links cannot be read, and offers no write", async () => {
		state.links = { data: undefined, isError: true };
		renderBlock();

		await userEvent.click(screen.getByRole("button", { name: /shared reports/i }));

		expect(screen.getByText("Shared reports aren't available right now.")).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "Share October" })).not.toBeInTheDocument();
	});
});

describe("describeReportLink", () => {
	// The sentence under each row is the whole of "what can my client see"
	// without opening the link, so each flag has to reach it.
	it.each([
		[true, true, "hours and amounts, with each entry"],
		[true, false, "hours and amounts, totals only"],
		[false, true, "hours only, with each entry"],
		[false, false, "hours only, totals only"],
	])("describes amounts=%s entries=%s", (showAmounts, showEntries, expected) => {
		expect(describeReportLink({ ...OCTOBER, showAmounts, showEntries })).toBe(expected);
	});
});
