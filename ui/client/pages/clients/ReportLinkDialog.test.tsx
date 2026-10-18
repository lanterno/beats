/**
 * The share dialog makes a link that opens a client's hours with no
 * sign-in, and shows its token once. What must hold: it cannot be made
 * without an expiry chosen; its days are finished ones; the preview follows
 * the form; the address is the SPA's own origin and the token after the #,
 * and Copy writes exactly that, or selects it where there is no clipboard;
 * the create is sent once, never again on a failure; once the dialog has
 * gone the token is nowhere, in the query cache or the page; and a
 * replace turns the old link off before making the new one.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReportLink, ReportLinkMade, ReportScopeInput } from "@/entities/report-link";
import type { PublicReport } from "@/shared/report";
import { ReportLinkDialog } from "./ReportLinkDialog";

const { api } = vi.hoisted(() => ({
	api: {
		createReportLink: vi.fn(),
		deleteReportLink: vi.fn(),
		previews: [] as { scope: ReportScopeInput; enabled: boolean }[],
	},
}));

const REPORT: PublicReport = {
	client_name: "Studio Kite",
	first: "2026-09-01",
	last: "2026-09-30",
	shows: { amounts: false, notes: false },
	billable_hours: 2.5,
	months: [
		{
			month: "2026-09",
			first: "2026-09-01",
			last: "2026-09-30",
			whole_month: true,
			billable_hours: 2.5,
			lines: [{ project_name: "Website", hours: 2.5 }],
			days: [{ day: "2026-09-16", project_name: "Website", hours: 2.5 }],
		},
	],
};

vi.mock("@/entities/report-link", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/report-link")>("@/entities/report-link");
	return {
		...actual,
		createReportLink: api.createReportLink,
		deleteReportLink: api.deleteReportLink,
		useReportPreview: (
			scope: ReportScopeInput,
			_tz: string,
			{ enabled = true }: { enabled?: boolean } = {},
		) => {
			api.previews.push({ scope, enabled });
			return { data: REPORT, error: null, isFetching: false };
		},
	};
});

const TOKEN = `lpr_${"A".repeat(43)}`;
const BILLED = [
	{ id: "p2", name: "Logo" },
	{ id: "p1", name: "Website" },
];
const OLD: ReportLink = {
	id: "old1",
	clientId: "c1",
	label: "September",
	first: "2026-09-01",
	last: "2026-09-30",
	tz: "Europe/Berlin",
	showAmounts: false,
	showNotes: false,
	projects: [{ id: "p1", name: "Website" }],
	expiresOn: "2026-12-31",
	createdAt: "2026-10-02T10:00:00Z",
	state: "live",
};

function made(): ReportLinkMade {
	return { link: { ...OLD, id: "new1" }, token: TOKEN };
}

/** The dialog the way a panel holds it: open until it asks to close. */
function Host({ replacing }: { replacing?: ReportLink }) {
	const [open, setOpen] = useState(true);
	return open ? (
		<ReportLinkDialog
			clientId="c1"
			clientName="Studio Kite"
			billedProjects={BILLED}
			replacing={replacing}
			onClose={() => setOpen(false)}
		/>
	) : (
		<p>closed</p>
	);
}

function renderDialog(replacing?: ReportLink) {
	const queryClient = new QueryClient();
	render(
		<QueryClientProvider client={queryClient}>
			<Host replacing={replacing} />
		</QueryClientProvider>,
	);
	return queryClient;
}

function setSecureContext(secure: boolean, writeText = vi.fn().mockResolvedValue(undefined)) {
	Object.defineProperty(window, "isSecureContext", { value: secure, configurable: true });
	Object.defineProperty(navigator, "clipboard", {
		value: secure ? { writeText } : undefined,
		configurable: true,
	});
	return writeText;
}

async function makeLink() {
	await userEvent.click(screen.getByRole("button", { name: "30 days" }));
	await userEvent.click(screen.getByRole("button", { name: "Create" }));
	return (await screen.findByLabelText("Report link")) as HTMLInputElement;
}

beforeEach(() => {
	vi.clearAllMocks();
	api.previews.length = 0;
});
afterEach(() => {
	cleanup();
	vi.useRealTimers();
});

describe("ReportLinkDialog", () => {
	it("Create stays disabled until an expiry is picked", async () => {
		renderDialog();
		const create = screen.getByRole("button", { name: "Create" });
		expect(create).toBeDisabled();
		for (const name of ["30 days", "90 days", "1 year"]) {
			expect(screen.getByRole("button", { name })).toHaveAttribute("aria-pressed", "false");
		}
		await userEvent.click(screen.getByRole("button", { name: "90 days" }));
		expect(create).toBeEnabled();
	});

	it("This month to yesterday is disabled on the 1st", () => {
		vi.useFakeTimers({ toFake: ["Date"] });
		vi.setSystemTime(new Date("2026-10-01T12:00:00Z"));
		renderDialog();
		expect(screen.getByRole("button", { name: "This month to yesterday" })).toBeDisabled();
		expect(screen.getByRole("button", { name: "Last month" })).toHaveAttribute(
			"aria-pressed",
			"true",
		);
	});

	it("the preview refetches when Show amounts is switched", async () => {
		renderDialog();
		expect(api.previews[api.previews.length - 1]?.scope).toMatchObject({
			showAmounts: false,
			showNotes: false,
		});
		await userEvent.click(screen.getByRole("checkbox", { name: /Show amounts/ }));
		await waitFor(() =>
			expect(api.previews[api.previews.length - 1]?.scope.showAmounts).toBe(true),
		);
	});

	it("the URL is the origin, /report#, the token, and Copy writes exactly it", async () => {
		const writeText = setSecureContext(true);
		api.createReportLink.mockResolvedValue(made());
		renderDialog();

		const field = await makeLink();
		const url = `${window.location.origin}/report#${TOKEN}`;
		expect(field).toHaveValue(url);
		await userEvent.click(screen.getByRole("button", { name: "Copy" }));
		expect(writeText).toHaveBeenCalledWith(url);
		expect(screen.getByText(/only time this link is shown/)).toBeVisible();
	});

	it("without a secure context Copy selects the field", async () => {
		setSecureContext(false);
		api.createReportLink.mockResolvedValue(made());
		renderDialog();

		const field = await makeLink();
		field.setSelectionRange(0, 0);
		await userEvent.click(screen.getByRole("button", { name: "Copy" }));
		expect(field).toHaveFocus();
		expect([field.selectionStart, field.selectionEnd]).toEqual([0, field.value.length]);
		expect(screen.getByText(/Press (⌘C|Ctrl\+C) to copy it/)).toBeVisible();
	});

	it("the create goes through post once, with no retry", async () => {
		api.createReportLink.mockRejectedValue(new Error("Network down"));
		renderDialog();

		await userEvent.click(screen.getByRole("button", { name: "30 days" }));
		await userEvent.click(screen.getByRole("button", { name: "Create" }));
		expect(await screen.findByRole("alert")).toHaveTextContent("Network down");
		await new Promise((resolve) => setTimeout(resolve, 50));
		expect(api.createReportLink).toHaveBeenCalledTimes(1);
		expect(api.createReportLink.mock.calls[0][0]).toMatchObject({
			clientId: "c1",
			projectIds: ["p2", "p1"],
			showAmounts: false,
			showNotes: false,
			label: undefined,
		});
	});

	it("after closing, the token is nowhere", async () => {
		setSecureContext(true);
		api.createReportLink.mockResolvedValue(made());
		const queryClient = renderDialog();

		await makeLink();
		await userEvent.click(screen.getByRole("button", { name: "Copy" }));
		await userEvent.click(screen.getByRole("button", { name: "Done" }));
		expect(await screen.findByText("closed")).toBeVisible();

		const cached = JSON.stringify([
			queryClient
				.getQueryCache()
				.getAll()
				.map((query) => query.state.data),
			queryClient
				.getMutationCache()
				.getAll()
				.map((mutation) => mutation.state.data),
		]);
		expect(cached).not.toContain(TOKEN);
		expect(document.body.innerHTML).not.toContain(TOKEN);
	});

	it("asks once before closing a link that was never copied", async () => {
		api.createReportLink.mockResolvedValue(made());
		renderDialog();

		await makeLink();
		await userEvent.click(screen.getByRole("button", { name: "Done" }));
		expect(await screen.findByText(/This link won't be shown again/)).toBeVisible();
		await userEvent.click(screen.getByRole("button", { name: "Keep it open" }));
		expect(screen.getByLabelText("Report link")).toBeVisible();

		await userEvent.click(screen.getByRole("button", { name: "Done" }));
		expect(await screen.findByText("closed")).toBeVisible();
	});

	it("Replace deletes first, and a failed create says the old link is off", async () => {
		const order: string[] = [];
		api.deleteReportLink.mockImplementation(async () => {
			order.push("delete");
		});
		api.createReportLink.mockImplementation(async () => {
			order.push("create");
			throw new Error("Server error");
		});
		renderDialog(OLD);

		// The form starts from the old link: its days, its project, its zone.
		expect(screen.getByLabelText("From")).toHaveValue("2026-09-01");
		expect(screen.getByRole("checkbox", { name: "Website" })).toBeChecked();
		expect(screen.getByRole("checkbox", { name: "Logo" })).not.toBeChecked();

		await userEvent.click(screen.getByRole("button", { name: "30 days" }));
		await userEvent.click(screen.getByRole("button", { name: "Create" }));
		expect(await screen.findByRole("alert")).toHaveTextContent(
			"The old link is off. Making the new one failed; try again.",
		);
		expect(order).toEqual(["delete", "create"]);
		expect(api.deleteReportLink).toHaveBeenCalledWith("old1");

		// Trying again makes a new link; the old one is not turned off twice.
		api.createReportLink.mockResolvedValue(made());
		await userEvent.click(screen.getByRole("button", { name: "Create" }));
		expect(await screen.findByLabelText("Report link")).toBeVisible();
		expect(api.deleteReportLink).toHaveBeenCalledTimes(1);
	});
});
