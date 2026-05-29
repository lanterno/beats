import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatHistoryMessage } from "./api/coachApi";
import { useCoachChat } from "./useCoachChat";

const fetchChatHistoryMock = vi.fn();

vi.mock("./api/coachApi", () => ({
	fetchChatHistory: (...args: unknown[]) => fetchChatHistoryMock(...args),
}));

describe("useCoachChat history restore", () => {
	beforeEach(() => fetchChatHistoryMock.mockReset());
	afterEach(() => vi.clearAllMocks());

	it("restores only the most recent conversation and resumes its id", async () => {
		const history: ChatHistoryMessage[] = [
			// An older conversation that must NOT bleed into the restored thread.
			{
				role: "user",
				content: "old q",
				created_at: "2026-05-01T09:00:00Z",
				conversation_id: "conv-1",
			},
			{
				role: "assistant",
				content: "old a",
				created_at: "2026-05-01T09:00:01Z",
				conversation_id: "conv-1",
			},
			// The most recent conversation.
			{
				role: "user",
				content: "new q",
				created_at: "2026-05-28T09:00:00Z",
				conversation_id: "conv-2",
			},
			{
				role: "assistant",
				content: "new a",
				created_at: "2026-05-28T09:00:01Z",
				conversation_id: "conv-2",
			},
		];
		fetchChatHistoryMock.mockResolvedValue(history);

		const { result } = renderHook(() => useCoachChat());

		await waitFor(() => expect(result.current.loadingHistory).toBe(false));
		expect(result.current.messages.map((m) => m.content)).toEqual(["new q", "new a"]);
		expect(result.current.conversationId).toBe("conv-2");
	});

	it("starts empty when there is no history", async () => {
		fetchChatHistoryMock.mockResolvedValue([]);
		const { result } = renderHook(() => useCoachChat());

		await waitFor(() => expect(result.current.loadingHistory).toBe(false));
		expect(result.current.messages).toEqual([]);
		expect(result.current.conversationId).toBeNull();
	});
});
