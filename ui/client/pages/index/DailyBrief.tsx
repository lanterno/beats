/**
 * DailyBrief — dashboard card showing today's AI-generated morning brief.
 * Fetches from GET /api/coach/brief/today. Shows a generate button if no
 * brief exists yet. Previous briefs are selectable via the history row, and
 * any brief shown can be rated; the coach reads recent ratings when it writes
 * the next one.
 */

import { Loader2, RefreshCw, Sparkles, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import {
	type BriefRating,
	type BriefResponse,
	useBriefFeedback,
	useCoachBrief,
	useCoachBriefHistory,
	useCoachStatus,
	useGenerateBrief,
} from "@/entities/coach";
import { cn } from "@/shared/lib";
import { Panel } from "@/shared/ui";

/** The mockup's `.lbl`: a panel's heading. */
const LABEL = "font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground";
const LINKISH =
	"text-accent-ink text-[12.5px] font-bold hover:underline underline-offset-[3px] rounded-full focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";

export function DailyBrief() {
	// On a server without the coach there is no brief to show or to write:
	// the card is left out, as the Coach nav item is.
	const { configured } = useCoachStatus();
	const { data: brief, isLoading } = useCoachBrief({ enabled: configured === true });
	const { data: history } = useCoachBriefHistory(14, { enabled: configured === true });
	const generate = useGenerateBrief();
	// null = today's brief; otherwise the date key of a past brief from history.
	const [selectedDate, setSelectedDate] = useState<string | null>(null);

	if (configured !== true || isLoading) return null;

	const selectedBrief =
		selectedDate !== null
			? (history?.find((b) => b.date === selectedDate) ?? null)
			: (brief ?? null);

	return (
		<section aria-label="Daily Brief">
			<Panel className="h-full">
				<header className="flex items-center gap-2 mb-3">
					<Sparkles className="w-3.5 h-3.5 text-muted-foreground" />
					<h2 className={LABEL}>Daily Brief</h2>
					{selectedDate !== null && (
						<button
							type="button"
							onClick={() => setSelectedDate(null)}
							className={cn(LINKISH, "ml-1")}
						>
							← Today
						</button>
					)}
					<button
						type="button"
						onClick={() => {
							setSelectedDate(null);
							generate.mutate(undefined);
						}}
						disabled={generate.isPending}
						className="ml-auto grid place-items-center w-7 h-7 -my-1 rounded-full text-muted-foreground hover:bg-sidebar-accent hover:text-foreground transition-colors disabled:opacity-50 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
						title={brief ? "Regenerate brief" : "Generate brief"}
					>
						{generate.isPending ? (
							<Loader2 className="w-3.5 h-3.5 animate-spin" />
						) : (
							<RefreshCw className="w-3.5 h-3.5" />
						)}
					</button>
				</header>

				{selectedDate !== null && (
					<p className="text-xs font-medium text-muted-foreground mb-2">Brief for {selectedDate}</p>
				)}

				{selectedBrief?.body ? (
					<>
						<div className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">
							{selectedBrief.body}
						</div>
						<BriefRatingRow brief={selectedBrief} />
					</>
				) : selectedDate !== null ? (
					<div className="text-[13px] font-medium text-muted-foreground text-center py-4">
						<p>No brief for this day.</p>
					</div>
				) : (
					<div className="text-[13px] font-medium text-muted-foreground text-center py-4">
						<p>No brief yet today.</p>
						<button
							type="button"
							onClick={() => generate.mutate(undefined)}
							disabled={generate.isPending}
							className={cn(LINKISH, "mt-2")}
						>
							{generate.isPending ? "Generating..." : "Generate now"}
						</button>
					</div>
				)}

				{history && history.length > 1 && (
					<div className="mt-3 pt-3 border-t border-border">
						<div className="flex gap-2 overflow-x-auto pb-1">
							{history.slice(1, 8).map((b) => (
								<button
									type="button"
									key={b.date}
									onClick={() => setSelectedDate(selectedDate === b.date ? null : b.date)}
									aria-pressed={selectedDate === b.date}
									className={cn(
										"shrink-0 px-2.5 py-0.5 rounded-full text-[11.5px] font-bold font-mono transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
										selectedDate === b.date
											? "bg-sidebar-accent text-foreground"
											: "bg-secondary text-muted-foreground hover:text-foreground",
									)}
									title={b.body?.slice(0, 200)}
								>
									{b.date}
								</button>
							))}
						</div>
					</div>
				)}
			</Panel>
		</section>
	);
}

const RATINGS: { rating: BriefRating; label: string; Icon: typeof ThumbsUp }[] = [
	{ rating: "helpful", label: "Helpful", Icon: ThumbsUp },
	{ rating: "not_useful", label: "Not useful", Icon: ThumbsDown },
];

/** "Was this useful?" — choosing the rating a brief already has clears it. */
function BriefRatingRow({ brief }: { brief: BriefResponse }) {
	const feedback = useBriefFeedback();
	// While a rating is on its way, show the one asked for.
	const current =
		feedback.isPending && feedback.variables.date === brief.date
			? feedback.variables.rating
			: (brief.feedback ?? null);

	return (
		<div className="mt-3 flex flex-wrap items-center gap-2">
			<span className="text-[12.5px] font-medium text-muted-foreground">Was this useful?</span>
			{RATINGS.map(({ rating, label, Icon }) => (
				<button
					type="button"
					key={rating}
					aria-pressed={current === rating}
					onClick={() =>
						feedback.mutate({ date: brief.date, rating: current === rating ? null : rating })
					}
					className={cn(
						"inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[12px] font-bold transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
						current === rating
							? "bg-foreground text-background"
							: "bg-secondary text-muted-foreground hover:text-foreground",
					)}
				>
					<Icon className="w-3 h-3" />
					{label}
				</button>
			))}
			{feedback.isError && (
				<span role="alert" className="text-[12px] font-medium text-destructive-ink">
					Couldn&apos;t save that.
				</span>
			)}
		</div>
	);
}
