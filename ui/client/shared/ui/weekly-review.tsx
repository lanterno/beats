/**
 * Weekly Review Dialog
 * Shown on Friday/Sunday evening. Three text areas: went well, didn't go well, to change.
 */

import { BookOpen, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useUpsertWeeklyReview, useWeeklyReview } from "@/entities/planning";
import { getMondayOfWeeksAgo } from "@/shared/lib";

const REVIEW_KEY = "beats_last_weekly_review";

export function WeeklyReviewDialog() {
	const [visible, setVisible] = useState(false);
	const thisMonday = getMondayOfWeeksAgo(0).toISOString().slice(0, 10);
	const { data: review } = useWeeklyReview(thisMonday);
	const upsertReview = useUpsertWeeklyReview();

	const [wentWell, setWentWell] = useState("");
	const [didntGoWell, setDidntGoWell] = useState("");
	const [toChange, setToChange] = useState("");

	// Show on Friday (5) or Sunday (0) evening (after 5pm)
	useEffect(() => {
		const now = new Date();
		const day = now.getDay();
		const hour = now.getHours();
		const isReviewTime = (day === 5 || day === 0) && hour >= 17;

		if (!isReviewTime) return;

		const weekKey = `${REVIEW_KEY}_${thisMonday}`;
		if (localStorage.getItem(weekKey)) return;

		const timer = setTimeout(() => setVisible(true), 1000);
		return () => clearTimeout(timer);
	}, [thisMonday]);

	useEffect(() => {
		if (review) {
			setWentWell(review.went_well || "");
			setDidntGoWell(review.didnt_go_well || "");
			setToChange(review.to_change || "");
		}
	}, [review]);

	const handleSave = useCallback(() => {
		upsertReview.mutate(
			{
				week_of: thisMonday,
				went_well: wentWell,
				didnt_go_well: didntGoWell,
				to_change: toChange,
			},
			{
				onSuccess: () => {
					toast.success("Weekly review saved");
					setVisible(false);
					localStorage.setItem(`${REVIEW_KEY}_${thisMonday}`, "1");
				},
			},
		);
	}, [upsertReview, thisMonday, wentWell, didntGoWell, toChange]);

	const dismiss = () => {
		setVisible(false);
		localStorage.setItem(`${REVIEW_KEY}_${thisMonday}`, "1");
	};

	if (!visible) return null;

	return (
		<div className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-sm">
			<div className="bg-card border border-border rounded-xl shadow-xl max-w-md w-full mx-4 overflow-hidden">
				<div className="flex items-center justify-between px-5 py-4 border-b border-border/40">
					<div className="flex items-center gap-2">
						<BookOpen className="w-5 h-5 text-accent" />
						<h2 className="text-base font-heading font-semibold text-foreground">Weekly Review</h2>
					</div>
					<button
						onClick={dismiss}
						className="p-1 rounded-md text-muted-foreground hover:text-foreground transition-colors"
					>
						<X className="w-4 h-4" />
					</button>
				</div>

				<div className="px-5 py-4 space-y-4">
					<div>
						<label className="block text-xs uppercase tracking-[0.1em] text-muted-foreground mb-1.5">
							What went well?
						</label>
						<textarea
							value={wentWell}
							onChange={(e) => setWentWell(e.target.value)}
							rows={2}
							className="w-full text-sm bg-secondary/50 border border-border rounded-md px-3 py-2 text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-accent resize-none"
							placeholder="Highlight wins and good habits..."
						/>
					</div>
					<div>
						<label className="block text-xs uppercase tracking-[0.1em] text-muted-foreground mb-1.5">
							What didn't go well?
						</label>
						<textarea
							value={didntGoWell}
							onChange={(e) => setDidntGoWell(e.target.value)}
							rows={2}
							className="w-full text-sm bg-secondary/50 border border-border rounded-md px-3 py-2 text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-accent resize-none"
							placeholder="What fell through the cracks..."
						/>
					</div>
					<div>
						<label className="block text-xs uppercase tracking-[0.1em] text-muted-foreground mb-1.5">
							What to change next week?
						</label>
						<textarea
							value={toChange}
							onChange={(e) => setToChange(e.target.value)}
							rows={2}
							className="w-full text-sm bg-secondary/50 border border-border rounded-md px-3 py-2 text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-accent resize-none"
							placeholder="Adjustments and experiments..."
						/>
					</div>
				</div>

				<div className="px-5 py-3 border-t border-border/40 flex gap-2">
					<button
						onClick={dismiss}
						className="flex-1 py-2 text-sm rounded-md border border-border text-foreground hover:bg-secondary/40 transition-colors"
					>
						Skip
					</button>
					<button
						onClick={handleSave}
						className="flex-1 py-2 text-sm font-medium rounded-md bg-accent text-accent-foreground hover:bg-accent/85 transition-colors"
					>
						Save Review
					</button>
				</div>
			</div>
		</div>
	);
}
