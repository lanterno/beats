/**
 * An account that signs in through single sign-on has no passkeys. The section once
 * read "no passkeys" as "still loading" and said Loading... forever.
 *
 * And a report link outlives every passkey: while some still open, the section says
 * how many, so removing a passkey is not taken to end them.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { listCredentials } = vi.hoisted(() => ({ listCredentials: vi.fn() }));

vi.mock("@/features/auth", () => ({ listCredentials, deleteCredential: vi.fn() }));

import { PasskeysSection } from "./PasskeysSection";

beforeEach(() => {
	vi.clearAllMocks();
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
		listCredentials.mockResolvedValue([
			{ id: "c1", device_name: "MacBook", created_at: "2026-01-02T00:00:00Z" },
		]);

		render(<PasskeysSection />);

		expect(await screen.findByText("MacBook")).toBeTruthy();
		expect(screen.queryByText("Loading...")).toBeNull();
	});

	it("names the live report links when there are some", async () => {
		listCredentials.mockResolvedValue([]);

		render(<PasskeysSection liveReportLinks={3} />);

		expect(
			await screen.findByText(
				"3 report links still work whatever happens to your passkeys; turn them off under Report links below.",
			),
		).toBeTruthy();
	});

	it("names none when there are none", async () => {
		listCredentials.mockResolvedValue([]);

		render(<PasskeysSection liveReportLinks={0} />);

		await screen.findByText(/No passkeys on this account/);
		expect(screen.queryByText(/report link/)).toBeNull();
	});
});
