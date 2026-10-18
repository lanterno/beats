/**
 * The page a client opens: without a token worth asking about it asks
 * nothing, every dead link reads the same, the tab's title never takes the
 * client's name, and a page brought back by the back-forward cache asks
 * again, so a link turned off meanwhile shows dead.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { HoursReport } from "@/shared/report";
import { ReportPage } from "./ReportPage";

const TOKEN = `lpr_${"b".repeat(43)}`;
const DEAD = /This report link isn't valid\. It may have been turned off or have ended/;

const REPORT: HoursReport = {
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

function answering(status: number, body: unknown) {
	const fetchMock = vi.fn(
		async () =>
			new Response(JSON.stringify(body), {
				status,
				headers: { "Content-Type": "application/json" },
			}),
	);
	vi.stubGlobal("fetch", fetchMock);
	return fetchMock;
}

beforeEach(() => {
	document.title = "Hours report";
});

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
	window.history.replaceState(null, "", "/");
});

describe("ReportPage", () => {
	it("no fragment makes no request and shows the dead message", () => {
		const fetchMock = answering(200, REPORT);
		window.history.replaceState(null, "", "/report");
		render(<ReportPage />);
		expect(screen.getByText(DEAD)).toBeTruthy();
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it("a malformed fragment makes no request either", () => {
		const fetchMock = answering(200, REPORT);
		window.history.replaceState(null, "", "/report#lpr_short");
		render(<ReportPage />);
		expect(screen.getByText(DEAD)).toBeTruthy();
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it("a 404 shows the same words", async () => {
		answering(404, { detail: "This report link isn't valid.", code: "REPORT_NOT_FOUND" });
		window.history.replaceState(null, "", `/report#${TOKEN}`);
		render(<ReportPage />);
		expect(await screen.findByText(DEAD)).toBeTruthy();
	});

	it("the title stays Hours report after loading", async () => {
		answering(200, REPORT);
		window.history.replaceState(null, "", `/report#${TOKEN}`);
		render(<ReportPage />);
		expect(await screen.findByRole("heading", { name: "Studio Kite" })).toBeTruthy();
		expect(document.title).toBe("Hours report");
	});

	it("a page restored from the back-forward cache fetches again", async () => {
		const fetchMock = answering(200, REPORT);
		window.history.replaceState(null, "", `/report#${TOKEN}`);
		render(<ReportPage />);
		await screen.findByRole("heading", { name: "Studio Kite" });
		expect(fetchMock).toHaveBeenCalledTimes(1);

		// A first load's pageshow is not a restore, and asks nothing.
		window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: false }));
		window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
	});
});
