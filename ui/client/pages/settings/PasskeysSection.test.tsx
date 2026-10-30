/**
 * An account that signs in through single sign-on has no passkeys. The section once
 * read "no passkeys" as "still loading" and said Loading... forever.
 *
 * Removing a passkey once took one click on the row's button, with no question asked.
 * It cannot be undone, and report links survive it, so it now asks first.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { listCredentials, deleteCredential, get } = vi.hoisted(() => ({
	listCredentials: vi.fn(),
	deleteCredential: vi.fn(),
	get: vi.fn(),
}));

vi.mock("@/features/auth", () => ({ listCredentials, deleteCredential }));
vi.mock("@/shared/api", async () => {
	const actual = await vi.importActual<typeof import("@/shared/api")>("@/shared/api");
	return { ...actual, get };
});

import { PasskeysSection } from "./PasskeysSection";

let queryClient: QueryClient;

function wrapper({ children }: { children: ReactNode }) {
	return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

const MAC = { id: "c1", device_name: "Mac", created_at: "2026-01-02T12:00:00Z" };
const IPHONE = { id: "c2", device_name: "iPhone", created_at: "2026-03-04T12:00:00Z" };
const KEY = { id: "c3", device_name: null, created_at: "2026-05-06T12:00:00Z" };

function apiClient(id: string, archived: boolean) {
	return {
		id,
		name: id,
		contact_name: null,
		contact_email: null,
		currency: "EUR",
		minor_units: 2,
		rates: [],
		archived,
		created_at: "2026-01-01T00:00:00Z",
		currency_locked: false,
	};
}

function apiLink(id: string, clientId: string) {
	return {
		id,
		client_id: clientId,
		token: `token-${id}`,
		first: "2026-10-01",
		last: "2026-10-31",
		tz: "Europe/Berlin",
		show_amounts: true,
		show_entries: false,
		created_at: "2026-10-30T00:00:00Z",
	};
}

const LINKS: Record<string, unknown> = {
	"/api/clients/studio/links": [apiLink("l1", "studio"), apiLink("l2", "studio")],
	"/api/clients/bakery/links": [apiLink("l3", "bakery")],
};

/** One active client with two links and one archived client with one. */
function withReportLinks(links: (path: string) => unknown = (path) => LINKS[path]) {
	get.mockImplementation(async (path: string) => {
		if (path === "/api/clients/?archived=false") return [apiClient("studio", false)];
		if (path === "/api/clients/?archived=true") return [apiClient("bakery", true)];
		return links(path);
	});
}

async function openRemoval(name: string) {
	render(<PasskeysSection />, { wrapper });
	await screen.findByText(name);
	// Remove only once the client lists are in, as they are in the app (the sidebar reads them).
	await waitFor(() => expect(queryClient.isFetching()).toBe(0));
	const row = screen.getByText(name).parentElement as HTMLElement;
	fireEvent.click(row.querySelector('button[title="Remove passkey"]') as HTMLElement);
	return screen.findByRole("dialog");
}

beforeEach(() => {
	vi.clearAllMocks();
	queryClient = new QueryClient({
		defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
	});
	get.mockResolvedValue([]);
	deleteCredential.mockResolvedValue(undefined);
});

afterEach(cleanup);

describe("PasskeysSection", () => {
	it("says Loading... until the list answers", () => {
		listCredentials.mockReturnValue(new Promise(() => {}));

		render(<PasskeysSection />, { wrapper });

		expect(screen.getByText("Loading...")).toBeTruthy();
	});

	it("says an account with no passkeys has none", async () => {
		listCredentials.mockResolvedValue([]);

		render(<PasskeysSection />, { wrapper });

		expect(await screen.findByText(/No passkeys on this account/)).toBeTruthy();
		expect(screen.queryByText("Loading...")).toBeNull();
	});

	it("lists the passkeys an account has", async () => {
		listCredentials.mockResolvedValue([MAC]);

		render(<PasskeysSection />, { wrapper });

		expect(await screen.findByText("Mac")).toBeTruthy();
		expect(screen.queryByText("Loading...")).toBeNull();
	});

	it("asks before removing a passkey, and Keep it removes nothing", async () => {
		listCredentials.mockResolvedValue([MAC, IPHONE, KEY]);

		const dialog = await openRemoval("Mac");

		expect(dialog).toHaveAccessibleName("Remove the Mac passkey?");
		expect(dialog).toHaveTextContent("stops signing you in on every device that holds it");
		expect(deleteCredential).not.toHaveBeenCalled();

		fireEvent.click(screen.getByRole("button", { name: "Keep it" }));

		await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
		expect(deleteCredential).not.toHaveBeenCalled();
	});

	it("removes the passkey once the question is answered", async () => {
		listCredentials.mockResolvedValue([MAC, IPHONE, KEY]);

		await openRemoval("iPhone");
		fireEvent.click(screen.getByRole("button", { name: "Remove" }));

		await waitFor(() => expect(deleteCredential).toHaveBeenCalledWith("c2"));
		await waitFor(() => expect(listCredentials).toHaveBeenCalledTimes(2));
	});

	it("names the passkey that will be the only one left", async () => {
		listCredentials.mockResolvedValue([MAC, IPHONE]);

		const dialog = await openRemoval("Mac");

		expect(dialog).toHaveTextContent("The iPhone passkey will be the only one left.");
	});

	it("says nothing of the last one while more than one will be left", async () => {
		listCredentials.mockResolvedValue([MAC, IPHONE, KEY]);

		const dialog = await openRemoval("Mac");

		expect(dialog).not.toHaveTextContent("only one left");
	});

	it("counts the report links still working, archived clients' too", async () => {
		listCredentials.mockResolvedValue([MAC, IPHONE, KEY]);
		withReportLinks();

		const dialog = await openRemoval("Mac");

		expect(dialog).toHaveTextContent("Your 3 report links keep working");
	});

	it("still asks when the report links cannot be counted", async () => {
		listCredentials.mockResolvedValue([MAC, IPHONE, KEY]);
		withReportLinks(() => Promise.reject(new TypeError("Failed to fetch")));

		const dialog = await openRemoval("Mac");

		expect(dialog).toHaveAccessibleName("Remove the Mac passkey?");
		expect(dialog).not.toHaveTextContent("report link");
	});
});
