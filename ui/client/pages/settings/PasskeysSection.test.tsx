/**
 * An account that signs in through single sign-on has no passkeys. The section once
 * read "no passkeys" as "still loading" and said Loading... forever.
 *
 * Removing a passkey once took one click on the row's button, with no question asked,
 * though it cannot be undone. It now asks first.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { listCredentials, deleteCredential } = vi.hoisted(() => ({
	listCredentials: vi.fn(),
	deleteCredential: vi.fn(),
}));

vi.mock("@/features/auth", () => ({ listCredentials, deleteCredential }));

import { PasskeysSection } from "./PasskeysSection";

const MAC = { id: "c1", device_name: "Mac", created_at: "2026-01-02T12:00:00Z" };
const IPHONE = { id: "c2", device_name: "iPhone", created_at: "2026-03-04T12:00:00Z" };
const KEY = { id: "c3", device_name: null, created_at: "2026-05-06T12:00:00Z" };

async function openRemoval(name: string) {
	render(<PasskeysSection />);
	await screen.findByText(name);
	const row = screen.getByText(name).parentElement as HTMLElement;
	fireEvent.click(row.querySelector('button[title="Remove passkey"]') as HTMLElement);
	return screen.findByRole("dialog");
}

beforeEach(() => {
	vi.clearAllMocks();
	deleteCredential.mockResolvedValue(undefined);
});

afterEach(cleanup);

describe("PasskeysSection", () => {
	it("says Loading... until the list answers", () => {
		listCredentials.mockReturnValue(new Promise(() => {}));

		render(<PasskeysSection />);

		expect(screen.getByText("Loading...")).toBeTruthy();
	});

	it("says an account with no passkeys has none", async () => {
		listCredentials.mockResolvedValue([]);

		render(<PasskeysSection />);

		expect(await screen.findByText(/No passkeys on this account/)).toBeTruthy();
		expect(screen.queryByText("Loading...")).toBeNull();
	});

	it("lists the passkeys an account has", async () => {
		listCredentials.mockResolvedValue([MAC]);

		render(<PasskeysSection />);

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
});
