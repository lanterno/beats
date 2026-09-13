/**
 * Coach page — AI chat with streaming + tool-use visualization.
 */

import { Brain, Loader2, RotateCcw, Send, Sparkles, Wrench } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { type ChatMessage, useCoachChat } from "@/entities/coach";
import { cn } from "@/shared/lib";
import { Button, Panel } from "@/shared/ui";
import { CoachMemoryDialog } from "./CoachMemoryDialog";

export default function Coach() {
	const { messages, streaming, currentTool, loadingHistory, sendMessage, stop, reset } =
		useCoachChat();
	const [input, setInput] = useState("");
	const [memoryOpen, setMemoryOpen] = useState(false);
	const bottomRef = useRef<HTMLDivElement>(null);
	const inputRef = useRef<HTMLTextAreaElement>(null);

	const handleSend = useCallback(() => {
		const text = input.trim();
		if (!text || streaming) return;
		setInput("");
		sendMessage(text);
	}, [input, streaming, sendMessage]);

	const handleKeyDown = useCallback(
		(e: React.KeyboardEvent) => {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				handleSend();
			}
		},
		[handleSend],
	);

	// messages.length and currentTool are *trigger* deps: they drive when the
	// scroll-to-bottom fires but aren't read inside the effect body. Biome's
	// useExhaustiveDependencies flags this as "extra deps", but removing them
	// breaks auto-scroll on new message / new tool. Suppression below applies.
	// biome-ignore lint/correctness/useExhaustiveDependencies: trigger-only deps
	useEffect(() => {
		bottomRef.current?.scrollIntoView({ behavior: "smooth" });
	}, [messages.length, currentTool]);

	useEffect(() => {
		inputRef.current?.focus();
	}, []);

	return (
		<div className="max-w-3xl mx-auto px-6 py-6 flex flex-col h-[calc(100vh-3rem)]">
			{/* Header */}
			<header className="flex items-center gap-2 mb-4">
				<Sparkles className="w-5 h-5 text-muted-foreground" />
				<h1 className="font-heading text-[22px] font-extrabold tracking-[-0.01em] text-foreground">
					Coach
				</h1>
				<div className="ml-auto flex items-center gap-2">
					<button
						type="button"
						onClick={() => setMemoryOpen(true)}
						className={HEADER_BUTTON}
						title="Coach memory"
					>
						<Brain className="w-4 h-4" />
					</button>
					{messages.length > 0 && (
						<button
							type="button"
							onClick={reset}
							className={HEADER_BUTTON}
							title="New conversation"
						>
							<RotateCcw className="w-4 h-4" />
						</button>
					)}
				</div>
			</header>

			{/* Messages — one panel, so the conversation reads on either hour's sky. */}
			<Panel padding="p-4 sm:p-5" className="flex-1 min-h-0 overflow-y-auto space-y-3">
				{loadingHistory && messages.length === 0 && (
					<div className="flex justify-center mt-20 text-muted-foreground">
						<Loader2 className="w-5 h-5 animate-spin" />
					</div>
				)}

				{!loadingHistory && messages.length === 0 && !streaming && (
					<div className="text-center text-muted-foreground mt-20 space-y-2">
						<Sparkles className="w-8 h-8 mx-auto opacity-60" />
						<p className="text-sm font-medium text-foreground">
							Ask the coach anything about your work.
						</p>
						<p className="text-xs text-muted-foreground">
							It can look up your sessions, projects, patterns, and scores.
						</p>
					</div>
				)}

				{messages.map((msg) => (
					<MessageBubble key={msg.id} message={msg} />
				))}

				{currentTool && (
					<div className="flex items-center gap-2 text-[12.5px] font-medium text-muted-foreground px-3 py-2">
						<Wrench className="w-3 h-3 animate-pulse" />
						Looking up {currentTool}...
					</div>
				)}

				<div ref={bottomRef} />
			</Panel>

			{/* Input */}
			<Panel padding="p-2" className="mt-3">
				<div className="flex items-end gap-2">
					<textarea
						ref={inputRef}
						value={input}
						onChange={(e) => setInput(e.target.value)}
						onKeyDown={handleKeyDown}
						placeholder="Ask about your work..."
						rows={1}
						className={cn(
							"flex-1 min-w-0 resize-none rounded-[1.25rem] bg-secondary px-3.5 py-2.5",
							"text-sm text-foreground placeholder:text-muted-foreground",
							"focus:outline-hidden focus:ring-[3px] focus:ring-accent",
						)}
					/>
					{streaming ? (
						<Button
							size="icon"
							variant="secondary"
							onClick={stop}
							className="shrink-0"
							title="Stop"
						>
							<Loader2 className="w-4 h-4 animate-spin" />
						</Button>
					) : (
						<Button
							size="icon"
							onClick={handleSend}
							disabled={!input.trim()}
							className="shrink-0"
							title="Send"
						>
							<Send className="w-4 h-4" />
						</Button>
					)}
				</div>
			</Panel>
			<CoachMemoryDialog open={memoryOpen} onClose={() => setMemoryOpen(false)} />
		</div>
	);
}

/** A round control on the sky: the panel with ink on it (the mockup's `.hdr .chip`). */
const HEADER_BUTTON =
	"grid place-items-center w-9 h-9 rounded-full bg-card text-muted-foreground shadow-soft hover:text-foreground transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

function MessageBubble({ message }: { message: ChatMessage }) {
	const isUser = message.role === "user";

	return (
		<div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
			<div
				className={cn(
					"max-w-[85%] rounded-[1.25rem] px-4 py-2.5 text-sm leading-relaxed text-foreground",
					// Yours on the heavier wash, the coach's on the lighter one.
					isUser ? "bg-sidebar-accent" : "bg-secondary",
				)}
			>
				<div className="whitespace-pre-wrap">{message.content}</div>

				{message.toolCalls && message.toolCalls.length > 0 && (
					<div className="mt-2 space-y-1 border-t border-border pt-2">
						{message.toolCalls.map((tc, i) => (
							<div
								key={`${tc.name}-${i}`}
								className="flex items-center gap-1.5 text-[11.5px] font-medium text-muted-foreground"
							>
								<Wrench className="w-3 h-3" />
								<span>{tc.name}</span>
								{tc.result && <span className="truncate max-w-[200px]">→ {tc.result}</span>}
							</div>
						))}
					</div>
				)}
			</div>
		</div>
	);
}
