/**
 * A run of absence writes: in order, each write tried twice, the first that
 * fails twice ending the run with the count of what landed, and the reads
 * invalidated once for the run rather than after every day.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { Absence } from "../model";

vi.mock("./absenceApi", () => ({
	fetchAbsences: vi.fn(),
	recordAbsence: vi.fn(),
	deleteAbsence: vi.fn(),
}));

import { recordAbsence } from "./absenceApi";
import { useRecordAbsences } from "./queries";

const SAVED: Absence = {
	id: "a1",
	projectId: "p1",
	date: "2026-09-14",
	type: "vacation",
	halfDay: false,
};

describe("useRecordAbsences", () => {
	it("writes in order, tries each twice, stops at the first that fails twice, and invalidates once", async () => {
		const queryClient = new QueryClient();
		const invalidate = vi.spyOn(queryClient, "invalidateQueries");
		const wrapper = ({ children }: { children: ReactNode }) => (
			<QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
		);
		vi.mocked(recordAbsence)
			.mockResolvedValueOnce(SAVED) // Mon
			.mockRejectedValueOnce(new Error("blip")) // Tue
			.mockResolvedValueOnce(SAVED) // Tue, again
			.mockRejectedValueOnce(new Error("down")) // Wed
			.mockRejectedValueOnce(new Error("still down")); // Wed, again: the run ends
		const { result } = renderHook(() => useRecordAbsences(), { wrapper });
		const dates = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17"];

		let writes: { done: number; error: unknown } | undefined;
		await act(async () => {
			writes = await result.current.mutateAsync({
				projectId: "p1",
				inputs: dates.map((date) => ({ date, type: "vacation" })),
			});
		});

		expect(writes?.done).toBe(2);
		expect(writes?.error).toEqual(new Error("still down"));
		expect(vi.mocked(recordAbsence).mock.calls.map(([, input]) => input.date)).toEqual([
			"2026-09-14",
			"2026-09-15",
			"2026-09-15",
			"2026-09-16",
			"2026-09-16",
		]);
		// The absences, the contract weeks, the ledger and the list: once each.
		expect(invalidate).toHaveBeenCalledTimes(4);
	});
});
