/**
 * DailyBrief — dashboard card showing today's AI-generated morning brief.
 * Fetches from GET /api/coach/brief/today. Shows a generate button if no
 * brief exists yet. Previous briefs accessible via horizontal scroll.
 */

import { Loader2, RefreshCw, Sparkles } from "lucide-react";
import { useCoachBrief, useCoachBriefHistory, useGenerateBrief } from "@/entities/coach";

export function DailyBrief() {
	const { data: brief, isLoading } = useCoachBrief();
	const { data: history } = useCoachBriefHistory();
	const generate = useGenerateBrief();

	if (isLoading) return null;

	return (
		<section
			aria-label="Daily Brief"
			className="rounded-xl border border-border/60 bg-card p-4 shadow-card"
		>
			<header className="flex items-center gap-2 mb-3">
				<Sparkles className="w-4 h-4 text-accent" />
				<h2 className="text-sm font-semibold text-foreground">Daily Brief</h2>
				<button
					type="button"
					onClick={() => generate.mutate(undefined)}
					disabled={generate.isPending}
					className="ml-auto p-1 rounded-md text-muted-foreground/60 hover:text-foreground hover:bg-secondary/50 transition disabled:opacity-50"
					title={brief ? "Regenerate brief" : "Generate brief"}
				>
					{generate.isPending ? (
						<Loader2 className="w-3.5 h-3.5 animate-spin" />
					) : (
						<RefreshCw className="w-3.5 h-3.5" />
					)}
				</button>
			</header>

			{brief?.body ? (
				<div className="text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">
					{brief.body}
				</div>
			) : (
				<div className="text-sm text-muted-foreground/70 text-center py-4">
					<p>No brief yet today.</p>
					<button
						type="button"
						onClick={() => generate.mutate(undefined)}
						disabled={generate.isPending}
						className="mt-2 text-accent hover:underline text-xs disabled:opacity-50"
					>
						{generate.isPending ? "Generating..." : "Generate now"}
					</button>
				</div>
			)}

			{history && history.length > 1 && (
				<div className="mt-3 pt-3 border-t border-border/40">
					<div className="flex gap-2 overflow-x-auto pb-1">
						{history.slice(1, 8).map((b) => (
							<button
								type="button"
								key={b.date}
								className="shrink-0 px-2 py-1 rounded text-[11px] text-muted-foreground/70 bg-secondary/30 hover:bg-secondary/50 transition"
								title={b.body?.slice(0, 200)}
							>
								{b.date}
							</button>
						))}
					</div>
				</div>
			)}
		</section>
	);
}
