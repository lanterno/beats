/**
 * The flow-window hooks key their query on "now". With the exact instant in
 * the key every render started a new query, and its result re-rendered: the
 * insights page fired ~500 identical requests in 2.5 s and eight flow cards
 * never left their loading state. Nothing about that is visible in a unit
 * test of the cards, so it is pinned here, on the key.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FlowWindowSummary } from "@/shared/api";

vi.mock("./sessionApi", async (importOriginal) => ({
	...(await importOriginal<typeof import("./sessionApi")>()),
	fetchFlowWindows: vi.fn(),
	fetchFlowWindowsSummary: vi.fn(),
}));

import { useFlowWindows, useFlowWindowsLastDays, useFlowWindowsSummary } from "./queries";
import { fetchFlowWindows, fetchFlowWindowsSummary } from "./sessionApi";

function wrapper(client: QueryClient) {
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

const cases: { name: string; hook: () => { isSuccess: boolean }; fetcher: unknown }[] = [
	{ name: "useFlowWindows", hook: () => useFlowWindows(), fetcher: fetchFlowWindows },
	{
		name: "useFlowWindowsLastDays",
		hook: () => useFlowWindowsLastDays(),
		fetcher: fetchFlowWindows,
	},
	{
		name: "useFlowWindowsSummary",
		hook: () => useFlowWindowsSummary(),
		fetcher: fetchFlowWindowsSummary,
	},
];

describe("flow-window hooks", () => {
	let client: QueryClient;

	beforeEach(() => {
		vi.useFakeTimers({ toFake: ["Date"] });
		vi.setSystemTime(new Date("2026-09-13T10:15:20.100Z"));
		client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
		vi.mocked(fetchFlowWindows).mockResolvedValue([]);
		vi.mocked(fetchFlowWindowsSummary).mockResolvedValue({} as FlowWindowSummary);
	});

	afterEach(() => {
		client.clear();
		vi.useRealTimers();
		vi.clearAllMocks();
	});

	it.each(cases)(
		"$name fetches once when it re-renders within the minute",
		async ({ hook, fetcher }) => {
			const { result, rerender } = renderHook(hook, { wrapper: wrapper(client) });
			await waitFor(() => expect(result.current.isSuccess).toBe(true));

			vi.setSystemTime(new Date("2026-09-13T10:15:21.350Z"));
			rerender();
			await waitFor(() => expect(result.current.isSuccess).toBe(true));

			expect(fetcher).toHaveBeenCalledTimes(1);
		},
	);
});
