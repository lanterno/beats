/**
 * Coach API functions — briefs, chat (SSE), and usage.
 */

import type { Schemas } from "@/shared/api";
import { get, post } from "@/shared/api";

export type BriefResponse = Schemas["BriefResponse"];
export type UsageSummaryResponse = Schemas["UsageSummaryResponse"];

export async function fetchTodayBrief(): Promise<BriefResponse | null> {
	return get<BriefResponse | null>("/api/coach/brief/today");
}

export async function fetchBriefHistory(limit = 14): Promise<BriefResponse[]> {
	return get<BriefResponse[]>(`/api/coach/brief/history?limit=${limit}`);
}

export async function generateBrief(date?: string): Promise<BriefResponse> {
	return post<BriefResponse>("/api/coach/brief/generate", date ? { date } : {});
}

export async function fetchUsage(days = 30): Promise<UsageSummaryResponse> {
	return get<UsageSummaryResponse>(`/api/coach/usage?days=${days}`);
}

export async function fetchChatHistory(
	conversationId?: string,
	limit = 50,
): Promise<Array<{ role: string; content: string; created_at: string; tool_calls?: unknown[] }>> {
	const params = new URLSearchParams({ limit: String(limit) });
	if (conversationId) params.set("conversation_id", conversationId);
	return get(`/api/coach/chat/history?${params}`);
}

export interface ChatSSEEvent {
	type: "text" | "tool_use" | "tool_result" | "done";
	text?: string;
	name?: string;
	input?: Record<string, unknown>;
	result?: string;
	conversation_id?: string;
}
