/**
 * Coach API functions — briefs, chat (SSE), and usage.
 */

import type { Schemas } from "@/shared/api";
import { del, get, post, put } from "@/shared/api";
import { browserTimeZone } from "@/shared/lib";

export type BriefResponse = Schemas["BriefResponse"];
export type UsageSummaryResponse = Schemas["UsageSummaryResponse"];
export type BriefRating = NonNullable<BriefResponse["feedback"]>;

// The coach's "today" (brief/review) is bucketed by the user's local
// calendar day server-side; send the browser timezone so a brief/review
// generated and fetched near midnight resolve to the same local day.

/**
 * Whether this server can run the coach at all: false when it has no
 * Anthropic API key, in which case every coach call answers 503
 * COACH_NOT_CONFIGURED and the SPA leaves the coach out.
 */
export async function fetchCoachStatus(): Promise<{ configured: boolean }> {
	return get<{ configured: boolean }>("/api/coach/status");
}

export async function fetchTodayBrief(): Promise<BriefResponse | null> {
	return get<BriefResponse | null>(
		`/api/coach/brief/today?tz=${encodeURIComponent(browserTimeZone())}`,
	);
}

export async function fetchBriefHistory(limit = 14): Promise<BriefResponse[]> {
	return get<BriefResponse[]>(`/api/coach/brief/history?limit=${limit}`);
}

export async function generateBrief(date?: string): Promise<BriefResponse> {
	const tz = encodeURIComponent(browserTimeZone());
	return post<BriefResponse>(`/api/coach/brief/generate?tz=${tz}`, date ? { date } : {});
}

/** Rate a brief, or clear its rating with null. The coach reads recent
 * ratings when it writes the next brief. */
export async function setBriefFeedback(
	date: string,
	rating: BriefRating | null,
): Promise<BriefResponse> {
	return put<BriefResponse>(`/api/coach/brief/${encodeURIComponent(date)}/feedback`, { rating });
}

export async function fetchUsage(days = 30): Promise<UsageSummaryResponse> {
	return get<UsageSummaryResponse>(`/api/coach/usage?days=${days}`);
}

export interface ChatHistoryMessage {
	role: string;
	content: string;
	created_at: string;
	conversation_id?: string;
	tool_calls?: unknown[];
}

export async function fetchChatHistory(
	conversationId?: string,
	limit = 50,
): Promise<ChatHistoryMessage[]> {
	const params = new URLSearchParams({ limit: String(limit) });
	if (conversationId) params.set("conversation_id", conversationId);
	return get(`/api/coach/chat/history?${params}`);
}

// ── Memory ──────────────────────────────────────────────────────────

export type MemoryResponse = Schemas["MemoryResponse"];

export async function fetchMemory(): Promise<MemoryResponse> {
	return get<MemoryResponse>("/api/coach/memory");
}

export async function rewriteMemory(): Promise<MemoryResponse> {
	const tz = encodeURIComponent(browserTimeZone());
	return post<MemoryResponse>(`/api/coach/memory/rewrite?tz=${tz}`, {});
}

export async function deleteMemory(): Promise<void> {
	await del<{ status: string }>("/api/coach/memory");
}

/**
 * Wipe ALL coach data (memory, briefs, reviews, conversations, usage).
 * Irreversible — the UI must confirm before calling this.
 */
export async function deleteCoachData(): Promise<void> {
	await del<{ status: string }>("/api/coach/data");
}

// ── Chat SSE ────────────────────────────────────────────────────────

export interface ChatSSEEvent {
	type: "text" | "tool_use" | "tool_result" | "done" | "error";
	text?: string;
	name?: string;
	input?: Record<string, unknown>;
	result?: string;
	conversation_id?: string;
	error?: string;
	code?: number;
}
