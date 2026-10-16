/**
 * An account that signs in through single sign-on has no passkeys. The section once
 * read "no passkeys" as "still loading" and said Loading... forever.
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
});
