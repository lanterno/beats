import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./intelligenceApi", () => ({
	dismissInboxItem: vi.fn(),
}));

import { dismissInboxItem } from "./intelligenceApi";
import { intelligenceKeys, useDismissInboxItem } from "./queries";

function wrapper(client: QueryClient) {
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

describe("useDismissInboxItem — projectHealth cache invalidation (FF.5)", () => {
	let client: QueryClient;
	let invalidateSpy: ReturnType<typeof vi.spyOn>;

	beforeEach(() => {
		client = new QueryClient({
			defaultOptions: { queries: { retry: false } },
		});
		invalidateSpy = vi.spyOn(client, "invalidateQueries");
		vi.mocked(dismissInboxItem).mockResolvedValue(undefined);
	});
	afterEach(() => {
		vi.clearAllMocks();
	});

	it("invalidates BOTH inbox and projectHealth when dismissing a 'project_health:*' id", async () => {
		const { result } = renderHook(() => useDismissInboxItem(), { wrapper: wrapper(client) });

		await act(async () => {
			await result.current.mutateAsync("project_health:proj-123");
		});

		await waitFor(() => {
			const calls = invalidateSpy.mock.calls.map(
				(c: { 0?: { queryKey?: readonly unknown[] } }) => c[0]?.queryKey,
			);
			expect(calls).toContainEqual(intelligenceKeys.inbox());
			expect(calls).toContainEqual(intelligenceKeys.projectHealth());
		});
	});

	it("does NOT invalidate projectHealth for non-project_health dismissals (pattern, suggestion)", async () => {
		const { result } = renderHook(() => useDismissInboxItem(), { wrapper: wrapper(client) });

		await act(async () => {
			await result.current.mutateAsync("pattern:bad-mornings");
		});

		await waitFor(() => {
			const calls = invalidateSpy.mock.calls.map(
				(c: { 0?: { queryKey?: readonly unknown[] } }) => c[0]?.queryKey,
			);
			expect(calls).toContainEqual(intelligenceKeys.inbox());
			expect(calls).not.toContainEqual(intelligenceKeys.projectHealth());
		});
	});
});
