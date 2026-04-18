/**
 * SSE streaming hook for coach chat. Not a TanStack Query hook — chat is
 * stateful and streaming, which doesn't map to query/mutation semantics.
 *
 * Returns sendMessage + live state (messages, streaming flag, tool activity).
 */

import { useCallback, useRef, useState } from "react";
import { getSessionToken } from "@/features/auth/stores/authStore";
import type { ChatSSEEvent } from "./api/coachApi";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:7999";

export interface ChatMessage {
	id: string;
	role: "user" | "assistant";
	content: string;
	toolCalls?: Array<{ name: string; input: Record<string, unknown>; result?: string }>;
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
	const abortRef = useRef<AbortController | null>(null);

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
		sendMessage,
		stop,
		reset,
	};
}
