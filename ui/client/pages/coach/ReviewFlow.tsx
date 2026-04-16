/**
 * ReviewFlow — Socratic end-of-day review modal.
 *
 * Presents 3 coach-generated questions one at a time. The user types freeform
 * answers which are persisted server-side and feed into the next day's brief
 * and the weekly memory rewrite.
 */

import { ChevronRight, Loader2, MessageCircle, X } from "lucide-react";
import { useCallback, useState } from "react";
import { useCoachReview, useStartReview, useSubmitReviewAnswer } from "@/entities/coach";
import { cn } from "@/shared/lib";

interface ReviewFlowProps {
	open: boolean;
	onClose: () => void;
}

export function ReviewFlow({ open, onClose }: ReviewFlowProps) {
	const { data: review } = useCoachReview();
	const startReview = useStartReview();
	const submitAnswer = useSubmitReviewAnswer();
	const [currentIndex, setCurrentIndex] = useState(0);
	const [answer, setAnswer] = useState("");

	const questions = review?.questions ?? [];
	const answers = review?.answers ?? [];
	const currentQuestion = questions[currentIndex];
	const isLastQuestion = currentIndex === questions.length - 1;

	const handleStart = useCallback(() => {
		startReview.mutate();
		setCurrentIndex(0);
		setAnswer("");
	}, [startReview]);

	const handleSubmit = useCallback(() => {
		if (!review?.date || !answer.trim()) return;

		submitAnswer.mutate({
			date: review.date,
			questionIndex: currentIndex,
			answer: answer.trim(),
		});

		if (!isLastQuestion) {
			setCurrentIndex((i) => i + 1);
			setAnswer("");
		} else {
			onClose();
			setCurrentIndex(0);
			setAnswer("");
		}
	}, [review?.date, currentIndex, answer, isLastQuestion, submitAnswer, onClose]);

	if (!open) return null;

	return (
		<div className="fixed inset-0 z-[90] flex items-center justify-center">
			<div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

			<div
				className="relative w-full max-w-lg rounded-xl border border-border bg-card shadow-card overflow-hidden"
				style={{ animation: "fadeSlideIn 200ms ease-out both" }}
			>
				{/* Header */}
				<div className="flex items-center justify-between px-5 py-4 border-b border-border/60">
					<div className="flex items-center gap-2">
						<MessageCircle className="w-4 h-4 text-accent" />
						<h2 className="text-sm font-semibold text-foreground">End-of-Day Review</h2>
					</div>
					<button
						type="button"
						onClick={onClose}
						className="p-1 rounded-md text-muted-foreground/60 hover:text-foreground transition"
					>
						<X className="w-4 h-4" />
					</button>
				</div>

				{/* Body */}
				<div className="px-5 py-6">
					{!review || questions.length === 0 ? (
						<div className="text-center space-y-3">
							<p className="text-sm text-muted-foreground">
								The coach will generate 3 questions based on your day.
							</p>
							<button
								type="button"
								onClick={handleStart}
								disabled={startReview.isPending}
								className={cn(
									"px-4 py-2 rounded-lg text-sm font-medium transition",
									"bg-accent text-accent-foreground hover:bg-accent/90",
									"disabled:opacity-50",
								)}
							>
								{startReview.isPending ? (
									<span className="flex items-center gap-2">
										<Loader2 className="w-3.5 h-3.5 animate-spin" />
										Generating...
									</span>
								) : (
									"Start review"
								)}
							</button>
						</div>
					) : (
						<div className="space-y-4">
							{/* Progress */}
							<div className="flex items-center gap-1.5">
								{questions.map((_, i) => (
									<div
										key={`q-${i}`}
										className={cn(
											"h-1 flex-1 rounded-full transition-colors",
											i < currentIndex
												? "bg-accent"
												: i === currentIndex
													? "bg-accent/60"
													: "bg-secondary/50",
										)}
									/>
								))}
							</div>

							{/* Question */}
							{currentQuestion && (
								<>
									<p className="text-sm text-foreground leading-relaxed">
										{currentQuestion.question}
									</p>

									<textarea
										value={answer}
										onChange={(e) => setAnswer(e.target.value)}
										placeholder="Your reflection..."
										rows={4}
										className={cn(
											"w-full rounded-lg border border-border/60 bg-secondary/20 px-3 py-2",
											"text-sm text-foreground placeholder:text-muted-foreground/50",
											"focus:outline-none focus:ring-1 focus:ring-accent/50 resize-none",
										)}
									/>

									<div className="flex justify-end">
										<button
											type="button"
											onClick={handleSubmit}
											disabled={!answer.trim() || submitAnswer.isPending}
											className={cn(
												"flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm",
												"font-medium transition",
												"bg-accent text-accent-foreground hover:bg-accent/90",
												"disabled:opacity-40",
											)}
										>
											{isLastQuestion ? "Finish" : "Next"}
											{!isLastQuestion && <ChevronRight className="w-3.5 h-3.5" />}
										</button>
									</div>

									{/* Previous answers */}
									{answers.slice(0, currentIndex).map(
										(a, i) =>
											a && (
												<div
													key={`a-${i}`}
													className="text-xs text-muted-foreground/60 border-l-2 border-border/40 pl-3 mt-2"
												>
													<span className="font-medium">Q{i + 1}:</span>{" "}
													{(a as { text?: string }).text?.slice(0, 100)}
												</div>
											),
									)}
								</>
							)}
						</div>
					)}
				</div>
			</div>
		</div>
	);
}
