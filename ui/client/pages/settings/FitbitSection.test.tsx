/**
 * The Fitbit OAuth return leg.
 *
 * Fitbit redirects the browser back to /settings?fitbit=callback&code=… and the
 * page has to exchange that code. A refactor dropped this handler once already,
 * and nothing caught it: the connect button still worked, the redirect still
 * happened, and the round trip simply ended on a page that ignored the code.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

import { FitbitSection } from "./FitbitSection";

function wrapper({ children }: { children: ReactNode }) {
	const client = new QueryClient({
		defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
	});
	return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function setUrl(search: string) {
	window.history.replaceState({}, "", `/settings${search}`);
}

beforeEach(() => {
	vi.clearAllMocks();
	get.mockResolvedValue({ connected: false });
	setUrl("");
});

afterEach(() => {
	cleanup();
	setUrl("");
});

describe("FitbitSection", () => {
	it("exchanges the code when Fitbit redirects back", async () => {
		setUrl("?fitbit=callback&code=abc123");
		post.mockResolvedValue(undefined);

		render(<FitbitSection />, { wrapper });

		await waitFor(() => expect(post).toHaveBeenCalledWith("/api/fitbit/connect?code=abc123"));
		await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Fitbit connected"));
	});

	it("cleans the code out of the URL afterwards", async () => {
		setUrl("?fitbit=callback&code=abc123");
		post.mockResolvedValue(undefined);

		render(<FitbitSection />, { wrapper });

		await waitFor(() => expect(window.location.search).toBe(""));
	});

	it("surfaces a failed exchange", async () => {
		setUrl("?fitbit=callback&code=bad");
		post.mockRejectedValue(new Error("nope"));

		render(<FitbitSection />, { wrapper });

		await waitFor(() => expect(toastError).toHaveBeenCalledWith("Failed to connect Fitbit"));
	});

	it("does nothing without a callback in the URL", async () => {
		render(<FitbitSection />, { wrapper });

		expect(await screen.findByRole("button", { name: /connect fitbit/i })).toBeInTheDocument();
		expect(post).not.toHaveBeenCalled();
	});

	it("percent-encodes the code", async () => {
		setUrl("?fitbit=callback&code=a%2Fb%20c");
		post.mockResolvedValue(undefined);

		render(<FitbitSection />, { wrapper });

		await waitFor(() => expect(post).toHaveBeenCalledWith("/api/fitbit/connect?code=a%2Fb%20c"));
	});
});
