/**
 * End-of-Day Review Component
 * Modal prompt for daily reflection: summary, text note, mood rating.
 */

import { Moon, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { cn, formatDuration } from "@/shared/lib";

const MOODS = [
	{ value: 1, label: "Rough", emoji: "😩" },
	{ value: 2, label: "Meh", emoji: "😕" },
	{ value: 3, label: "Okay", emoji: "😐" },
	{ value: 4, label: "Good", emoji: "🙂" },
	{ value: 5, label: "Great", emoji: "😊" },
];

const REVIEW_DISMISSED_KEY = "beats_review_dismissed";
const REVIEW_HOUR = 17; // 5 PM

interface EndOfDayReviewProps {
	totalMinutesToday: number;
	sessionCount: number;
	topProjectName?: string;
	existingNote?: string;
	existingMood?: number;
	onSave: (note: string, mood?: number) => void;
}

export function EndOfDayReview({
	totalMinutesToday,
	sessionCount,
	topProjectName,
	existingNote,
	existingMood,
	onSave,
}: EndOfDayReviewProps) {
	const [open, setOpen] = useState(false);
	const [note, setNote] = useState(existingNote ?? "");
	const [mood, setMood] = useState<number | undefined>(existingMood);

	useEffect(() => {
		// Check if it's after REVIEW_HOUR and we haven't dismissed today
		const now = new Date();
		const today = now.toISOString().slice(0, 10);
		const dismissed = localStorage.getItem(REVIEW_DISMISSED_KEY);

		if (now.getHours() >= REVIEW_HOUR && dismissed !== today && totalMinutesToday > 0) {
			const timer = setTimeout(() => setOpen(true), 2000);
			return () => clearTimeout(timer);
		}
	}, [totalMinutesToday]);

	const dismiss = useCallback(() => {
		const today = new Date().toISOString().slice(0, 10);
		localStorage.setItem(REVIEW_DISMISSED_KEY, today);
		setOpen(false);
	}, []);

	const handleSave = () => {
		onSave(note, mood);
		dismiss();
	};

	// Escape closes the dialog. Listening at the document level (rather
	// than a key handler on the panel) means the user doesn't need to
	// land focus inside the modal first — pressing Esc anywhere works,
	// matching native dialog behavior.
	useEffect(() => {
		if (!open) return;
		const onKey = (e: KeyboardEvent) => {
			if (e.key === "Escape") dismiss();
		};
		window.addEventListener("keydown", onKey);
		return () => window.removeEventListener("keydown", onKey);
	}, [open, dismiss]);

	if (!open) return null;

	return (
		<div className="fixed inset-0 z-[150] flex items-center justify-center">
			<button
				type="button"
				aria-label="Dismiss end-of-day review"
				className="absolute inset-0 bg-black/50 backdrop-blur-sm cursor-default"
				onClick={dismiss}
			/>
			<div
				role="dialog"
				aria-modal="true"
				aria-labelledby="eod-review-title"
				className="relative w-full max-w-sm rounded-xl border border-border bg-card shadow-card overflow-hidden mx-4"
				style={{ animation: "fadeSlideIn 200ms ease-out both" }}
			>
				{/* Header */}
				<div className="flex items-center justify-between px-5 py-4 border-b border-border/40">
					<div className="flex items-center gap-2">
						<Moon className="w-4 h-4 text-accent" aria-hidden="true" />
						<span id="eod-review-title" className="text-sm font-medium text-foreground">
							How was your day?
						</span>
					</div>
					<button
						type="button"
						onClick={dismiss}
						aria-label="Close"
						className="p-1 text-muted-foreground/40 hover:text-muted-foreground transition-colors"
					>
						<X className="w-4 h-4" aria-hidden="true" />
					</button>
				</div>

				<div className="px-5 py-4 space-y-4">
					{/* Today's summary */}
					<div className="flex items-center gap-4 text-center">
						<div className="flex-1">
							<p className="text-lg font-heading font-semibold tabular-nums text-accent">
								{formatDuration(totalMinutesToday)}
							</p>
							<p className="text-[10px] uppercase tracking-widest text-muted-foreground">tracked</p>
						</div>
						<div className="w-px h-8 bg-border/40" />
						<div className="flex-1">
							<p className="text-lg font-heading font-semibold tabular-nums text-foreground">
								{sessionCount}
							</p>
							<p className="text-[10px] uppercase tracking-widest text-muted-foreground">
								sessions
							</p>
						</div>
						{topProjectName && (
							<>
								<div className="w-px h-8 bg-border/40" />
								<div className="flex-1">
									<p className="text-sm font-medium text-foreground truncate">{topProjectName}</p>
									<p className="text-[10px] uppercase tracking-widest text-muted-foreground">
										top project
									</p>
								</div>
							</>
						)}
					</div>

					{/* Mood selector */}
					<div>
						<p className="text-xs text-muted-foreground mb-2">How do you feel?</p>
						<div className="flex gap-1">
							{MOODS.map((m) => (
								<button
									type="button"
									key={m.value}
									onClick={() => setMood(mood === m.value ? undefined : m.value)}
									className={cn(
										"flex-1 py-2 rounded-md text-center transition-all text-lg",
										mood === m.value
											? "bg-accent/15 ring-1 ring-accent/40 scale-110"
											: "hover:bg-secondary/40",
									)}
									title={m.label}
									aria-label={`Mood: ${m.label}`}
									aria-pressed={mood === m.value}
								>
									<span aria-hidden="true">{m.emoji}</span>
								</button>
							))}
						</div>
					</div>

					{/* Note */}
					<textarea
						value={note}
						onChange={(e) => setNote(e.target.value)}
						placeholder="Any thoughts about today? (optional)"
						rows={3}
						className="w-full rounded-md border border-border bg-secondary/30 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-accent/40 resize-none"
					/>

					{/* Actions */}
					<div className="flex gap-2">
						<button
							type="button"
							onClick={dismiss}
							className="flex-1 px-3 py-2 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-secondary/40 transition-colors"
						>
							Skip
						</button>
						<button
							type="button"
							onClick={handleSave}
							className="flex-1 px-3 py-2 rounded-md text-sm font-medium bg-accent text-accent-foreground hover:bg-accent/85 transition-colors"
						>
							Save
						</button>
					</div>
				</div>
			</div>
		</div>
	);
}
