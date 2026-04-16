/**
 * Coach page — AI chat with streaming + tool-use visualization.
 */

import { Loader2, MessageCircle, RotateCcw, Send, Sparkles, Wrench } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { type ChatMessage, useCoachChat } from "@/entities/coach";
import { cn } from "@/shared/lib";
import { ReviewFlow } from "./ReviewFlow";

export default function Coach() {
	const { messages, streaming, currentTool, sendMessage, stop, reset } = useCoachChat();
	const [input, setInput] = useState("");
	const [reviewOpen, setReviewOpen] = useState(false);
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

	// biome-ignore lint/correctness/useExhaustiveDependencies: scroll triggers on state changes
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
				<Sparkles className="w-5 h-5 text-accent" />
				<h1 className="text-lg font-heading font-bold text-foreground">Coach</h1>
				<div className="ml-auto flex items-center gap-1">
					<button
						type="button"
						onClick={() => setReviewOpen(true)}
						className="p-1.5 rounded-md text-muted-foreground/60 hover:text-foreground hover:bg-secondary/50 transition"
						title="End-of-day review"
					>
						<MessageCircle className="w-4 h-4" />
					</button>
					{messages.length > 0 && (
						<button
							type="button"
							onClick={reset}
							className="p-1.5 rounded-md text-muted-foreground/60 hover:text-foreground hover:bg-secondary/50 transition"
							title="New conversation"
						>
							<RotateCcw className="w-4 h-4" />
						</button>
					)}
				</div>
			</header>

			{/* Messages */}
			<div className="flex-1 overflow-y-auto space-y-4 pb-4">
				{messages.length === 0 && !streaming && (
					<div className="text-center text-muted-foreground/60 mt-20 space-y-2">
						<Sparkles className="w-8 h-8 mx-auto opacity-40" />
						<p className="text-sm">Ask the coach anything about your work.</p>
						<p className="text-xs text-muted-foreground/40">
							It can look up your sessions, projects, patterns, and scores.
						</p>
					</div>
				)}

				{messages.map((msg) => (
					<MessageBubble key={msg.id} message={msg} />
				))}

				{currentTool && (
					<div className="flex items-center gap-2 text-xs text-muted-foreground/70 px-3 py-2">
						<Wrench className="w-3 h-3 animate-pulse" />
						Looking up {currentTool}...
					</div>
				)}

				<div ref={bottomRef} />
			</div>

			{/* Input */}
			<div className="border-t border-border/60 pt-3">
				<div className="flex items-end gap-2">
					<textarea
						ref={inputRef}
						value={input}
						onChange={(e) => setInput(e.target.value)}
						onKeyDown={handleKeyDown}
						placeholder="Ask about your work..."
						rows={1}
						className={cn(
							"flex-1 resize-none rounded-lg border border-border/60 bg-secondary/20 px-3 py-2",
							"text-sm text-foreground placeholder:text-muted-foreground/50",
							"focus:outline-none focus:ring-1 focus:ring-accent/50",
						)}
					/>
					{streaming ? (
						<button
							type="button"
							onClick={stop}
							className="p-2 rounded-lg bg-secondary/50 text-muted-foreground hover:bg-secondary transition"
							title="Stop"
						>
							<Loader2 className="w-4 h-4 animate-spin" />
						</button>
					) : (
						<button
							type="button"
							onClick={handleSend}
							disabled={!input.trim()}
							className="p-2 rounded-lg bg-accent text-accent-foreground hover:bg-accent/90 transition disabled:opacity-40"
							title="Send"
						>
							<Send className="w-4 h-4" />
						</button>
					)}
				</div>
			</div>
			<ReviewFlow open={reviewOpen} onClose={() => setReviewOpen(false)} />
		</div>
	);
}

function MessageBubble({ message }: { message: ChatMessage }) {
	const isUser = message.role === "user";

	return (
		<div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
			<div
				className={cn(
					"max-w-[85%] rounded-xl px-4 py-2.5 text-sm leading-relaxed",
					isUser ? "bg-accent/15 text-foreground" : "bg-secondary/30 text-foreground/90",
				)}
			>
				<div className="whitespace-pre-wrap">{message.content}</div>

				{message.toolCalls && message.toolCalls.length > 0 && (
					<div className="mt-2 space-y-1 border-t border-border/30 pt-2">
						{message.toolCalls.map((tc, i) => (
							<div
								key={`${tc.name}-${i}`}
								className="flex items-center gap-1.5 text-[11px] text-muted-foreground/60"
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
