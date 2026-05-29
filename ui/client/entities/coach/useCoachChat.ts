/**
 * SSE streaming hook for coach chat. Not a TanStack Query hook — chat is
 * stateful and streaming, which doesn't map to query/mutation semantics.
 *
 * Returns sendMessage + live state (messages, streaming flag, tool activity).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { getSessionToken } from "@/features/auth/stores/authStore";
import { type ChatHistoryMessage, type ChatSSEEvent, fetchChatHistory } from "./api/coachApi";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:7999";

export interface ChatMessage {
	id: string;
	role: "user" | "assistant";
	content: string;
	toolCalls?: Array<{ name: string; input: Record<string, unknown>; result?: string }>;
}

/**
 * Turn raw chat-history rows into renderable messages, resuming only the most
 * recent conversation (the history endpoint can interleave threads when no
 * conversation_id is given). Tool calls aren't reconstructed for restored
 * history — past messages render as plain text bubbles.
 */
function restoreConversation(history: ChatHistoryMessage[]): {
	messages: ChatMessage[];
	conversationId: string | null;
} {
	if (history.length === 0) return { messages: [], conversationId: null };
	const lastConversationId = history[history.length - 1].conversation_id ?? null;
	const rows = lastConversationId
		? history.filter((m) => m.conversation_id === lastConversationId)
		: history;
	const messages: ChatMessage[] = rows
		.filter((m) => m.role === "user" || m.role === "assistant")
		.map((m, i) => ({
			id: `hist-${i}-${m.created_at}`,
			role: m.role as "user" | "assistant",
			content: m.content,
		}));
	return { messages, conversationId: lastConversationId };
}

interface CoachChatState {
	messages: ChatMessage[];
	streaming: boolean;
	conversationId: string | null;
	currentTool: string | null;
}

export function useCoachChat() {
	const [state, setState] = useState<CoachChatState>({
		messages: [],
		streaming: false,
		conversationId: null,
		currentTool: null,
	});
	const [loadingHistory, setLoadingHistory] = useState(true);
	const abortRef = useRef<AbortController | null>(null);
	const historyLoadedRef = useRef(false);

	// Restore the most recent conversation once on mount so the thread survives
	// a reload/navigation instead of starting empty every time.
	useEffect(() => {
		if (historyLoadedRef.current) return;
		historyLoadedRef.current = true;
		let cancelled = false;
		(async () => {
			try {
				const history = await fetchChatHistory();
				if (cancelled) return;
				const { messages, conversationId } = restoreConversation(history);
				if (messages.length > 0) {
					setState((prev) =>
						// Don't clobber a conversation the user already started before
						// history arrived.
						prev.messages.length > 0 ? prev : { ...prev, messages, conversationId },
					);
				}
			} catch {
				// Start fresh if history can't be loaded.
			} finally {
				if (!cancelled) setLoadingHistory(false);
			}
		})();
		return () => {
			cancelled = true;
		};
	}, []);

	const sendMessage = useCallback(
		async (text: string) => {
			const userMsg: ChatMessage = {
				id: `user-${Date.now()}`,
				role: "user",
				content: text,
			};

			setState((prev) => ({
				...prev,
				messages: [...prev.messages, userMsg],
				streaming: true,
				currentTool: null,
			}));

			const controller = new AbortController();
			abortRef.current = controller;

			const token = getSessionToken();
			const body = JSON.stringify({
				message: text,
				conversation_id: state.conversationId,
			});

			try {
				const res = await fetch(`${API_URL}/api/coach/chat`, {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						...(token ? { Authorization: `Bearer ${token}` } : {}),
					},
					body,
					signal: controller.signal,
				});

				if (!res.ok || !res.body) {
					const errText = await res.text().catch(() => "Chat failed");
					setState((prev) => ({
						...prev,
						streaming: false,
						messages: [
							...prev.messages,
							{
								id: `err-${Date.now()}`,
								role: "assistant",
								content: `Error: ${errText}`,
							},
						],
					}));
					return;
				}

				const reader = res.body.getReader();
				const decoder = new TextDecoder();
				let buffer = "";
				let assistantText = "";
				const toolCalls: ChatMessage["toolCalls"] = [];

				const assistantId = `asst-${Date.now()}`;

				while (true) {
					const { done, value } = await reader.read();
					if (done) break;

					buffer += decoder.decode(value, { stream: true });
					const lines = buffer.split("\n");
					buffer = lines.pop() ?? "";

					for (const line of lines) {
						if (!line.startsWith("data: ")) continue;
						const payload = line.slice(6).trim();
						if (payload === "[DONE]") continue;

						try {
							const event: ChatSSEEvent = JSON.parse(payload);

							if (event.type === "text" && event.text) {
								assistantText += event.text;
								setState((prev) => {
									const msgs = [...prev.messages];
									const existing = msgs.findIndex((m) => m.id === assistantId);
									const msg: ChatMessage = {
										id: assistantId,
										role: "assistant",
										content: assistantText,
										toolCalls: toolCalls.length > 0 ? [...toolCalls] : undefined,
									};
									if (existing >= 0) {
										msgs[existing] = msg;
									} else {
										msgs.push(msg);
									}
									return { ...prev, messages: msgs, currentTool: null };
								});
							}

							if (event.type === "tool_use" && event.name) {
								toolCalls.push({ name: event.name, input: event.input ?? {} });
								setState((prev) => ({ ...prev, currentTool: event.name ?? null }));
							}

							if (event.type === "tool_result" && event.name) {
								const tc = toolCalls.find((t) => t.name === event.name && !t.result);
								if (tc) tc.result = event.result;
								setState((prev) => ({ ...prev, currentTool: null }));
							}

							if (event.type === "error") {
								assistantText += `\n\n${event.error ?? "Something went wrong."}`;
								setState((prev) => {
									const msgs = [...prev.messages];
									const existing = msgs.findIndex((m) => m.id === assistantId);
									const msg: ChatMessage = {
										id: assistantId,
										role: "assistant",
										content: assistantText,
									};
									if (existing >= 0) {
										msgs[existing] = msg;
									} else {
										msgs.push(msg);
									}
									return { ...prev, messages: msgs, streaming: false };
								});
							}

							if (event.type === "done" && event.conversation_id) {
								setState((prev) => ({
									...prev,
									conversationId: event.conversation_id ?? null,
									streaming: false,
								}));
							}
						} catch {
							// skip malformed events
						}
					}
				}

				setState((prev) => ({ ...prev, streaming: false }));
			} catch (err) {
				if ((err as Error).name !== "AbortError") {
					setState((prev) => ({
						...prev,
						streaming: false,
						messages: [
							...prev.messages,
							{
								id: `err-${Date.now()}`,
								role: "assistant",
								content: "Connection lost. Try again.",
							},
						],
					}));
				}
			}
		},
		[state.conversationId],
	);

	const stop = useCallback(() => {
		abortRef.current?.abort();
		setState((prev) => ({ ...prev, streaming: false, currentTool: null }));
	}, []);

	const reset = useCallback(() => {
		abortRef.current?.abort();
		setState({
			messages: [],
			streaming: false,
			conversationId: null,
			currentTool: null,
		});
	}, []);

	return {
		messages: state.messages,
		streaming: state.streaming,
		conversationId: state.conversationId,
		currentTool: state.currentTool,
		loadingHistory,
		sendMessage,
		stop,
		reset,
	};
}
