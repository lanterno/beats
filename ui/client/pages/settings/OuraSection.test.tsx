/**
 * Tests for the Oura integration section, standing in for the shared
 * `useIntegration` + `IntegrationSection` pair underneath it.
 *
 * These sections previously hand-rolled their own fetch/loading cycle and
 * swallowed every failure in a bare `catch {}` — a disconnect that 500'd left
 * the UI claiming the account was still connected, with nothing on screen. The
 * cases below pin the states that were unobservable before.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// vi.mock factories are hoisted above the file, so the spies they close over
// have to be created with vi.hoisted.
const { get, post, del, toastSuccess, toastError } = vi.hoisted(() => ({
	get: vi.fn(),
	post: vi.fn(),
	del: vi.fn(),
	toastSuccess: vi.fn(),
	toastError: vi.fn(),
}));

vi.mock("@/shared/api", async () => {
	const actual = await vi.importActual<typeof import("@/shared/api")>("@/shared/api");
	return { ...actual, get, post, del };
});

vi.mock("sonner", () => ({ toast: { success: toastSuccess, error: toastError } }));

import { OuraSection } from "./OuraSection";

function wrapper({ children }: { children: ReactNode }) {
	const client = new QueryClient({
		defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
	});
	return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
	vi.clearAllMocks();
	get.mockResolvedValue({ connected: false });
});

afterEach(cleanup);

describe("OuraSection", () => {
	it("offers a token field when not connected", async () => {
		render(<OuraSection />, { wrapper });

		expect(await screen.findByPlaceholderText(/personal access token/i)).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: /disconnect/i })).not.toBeInTheDocument();
	});

	it("shows a disconnect control once connected", async () => {
		get.mockResolvedValue({ connected: true });

		render(<OuraSection />, { wrapper });

		expect(await screen.findByRole("button", { name: /disconnect/i })).toBeInTheDocument();
		expect(screen.queryByPlaceholderText(/personal access token/i)).not.toBeInTheDocument();
	});

	it("keeps Connect disabled until a token is typed", async () => {
		render(<OuraSection />, { wrapper });

		const connect = await screen.findByRole("button", { name: /^connect$/i });
		expect(connect).toBeDisabled();

		await userEvent.type(await screen.findByPlaceholderText(/personal access token/i), "tok_123");
		expect(connect).toBeEnabled();
	});

	it("posts the trimmed token and clears the field", async () => {
		post.mockResolvedValue(undefined);
		render(<OuraSection />, { wrapper });

		const field = await screen.findByPlaceholderText(/personal access token/i);
		await userEvent.type(field, "  tok_123  ");
		await userEvent.click(screen.getByRole("button", { name: /^connect$/i }));

		await waitFor(() =>
			expect(post).toHaveBeenCalledWith("/api/oura/connect", { access_token: "tok_123" }),
		);
		expect(field).toHaveValue("");
	});

	it("surfaces a failed connect instead of swallowing it", async () => {
		post.mockRejectedValue(new Error("Invalid token [OURA_REJECTED]"));
		render(<OuraSection />, { wrapper });

		await userEvent.type(await screen.findByPlaceholderText(/personal access token/i), "bad");
		await userEvent.click(screen.getByRole("button", { name: /^connect$/i }));

		await waitFor(() => expect(toastError).toHaveBeenCalled());
		expect(toastError.mock.calls[0][0]).toMatch(/Invalid token \[OURA_REJECTED\]/);
	});

	it("surfaces a failed disconnect", async () => {
		get.mockResolvedValue({ connected: true });
		del.mockRejectedValue(new Error("boom"));
		render(<OuraSection />, { wrapper });

		await userEvent.click(await screen.findByRole("button", { name: /disconnect/i }));

		await waitFor(() => expect(toastError).toHaveBeenCalled());
		expect(toastError.mock.calls[0][0]).toMatch(/boom|Failed to disconnect Oura/);
	});
});
