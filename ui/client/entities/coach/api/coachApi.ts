/**
 * Coach API functions — briefs, chat (SSE), and usage.
 */

import type { Schemas } from "@/shared/api";
import { del, get, post } from "@/shared/api";

export type BriefResponse = Schemas["BriefResponse"];
export type UsageSummaryResponse = Schemas["UsageSummaryResponse"];

// The coach's "today" (brief/review) is bucketed by the user's local
// calendar day server-side; send the browser timezone so a brief/review
// generated and fetched near midnight resolve to the same local day.
const browserTimeZone = (): string => Intl.DateTimeFormat().resolvedOptions().timeZone;

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

// ── Reviews ─────────────────────────────────────────────────────────

export type ReviewResponse = Schemas["ReviewResponse"];

export async function startReview(): Promise<ReviewResponse> {
	return post<ReviewResponse>(
		`/api/coach/review/start?tz=${encodeURIComponent(browserTimeZone())}`,
		{},
	);
}

export async function fetchTodayReview(): Promise<ReviewResponse | null> {
	return get<ReviewResponse | null>(
		`/api/coach/review/today?tz=${encodeURIComponent(browserTimeZone())}`,
	);
}

export async function submitReviewAnswer(
	reviewDate: string,
	questionIndex: number,
	answer: string,
): Promise<void> {
	await post("/api/coach/review/answer", {
		date: reviewDate,
		question_index: questionIndex,
		answer,
	});
}

// ── Memory ──────────────────────────────────────────────────────────

export type MemoryResponse = Schemas["MemoryResponse"];

export async function fetchMemory(): Promise<MemoryResponse> {
	return get<MemoryResponse>("/api/coach/memory");
}

export async function rewriteMemory(): Promise<MemoryResponse> {
	return post<MemoryResponse>("/api/coach/memory/rewrite", {});
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
