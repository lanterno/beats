/**
 * PatternCards Component
 * Grid of dismissible insight cards from pattern detection.
 */

import { RefreshCw, Sparkles, X } from "lucide-react";
import { useDismissPattern, usePatterns, useRefreshPatterns } from "@/entities/intelligence";
import { cn } from "@/shared/lib";

const typeIcons: Record<string, string> = {
	day_pattern: "📅",
	time_pattern: "⏰",
	stale_project: "💤",
	mood_correlation: "🧠",
	session_trend: "📊",
	estimation_accuracy: "🎯",
	goal_pacing: "🏃",
};

export function PatternCards() {
	const { data: patterns } = usePatterns();
	const refreshMutation = useRefreshPatterns();
	const dismissMutation = useDismissPattern();

	const insights = patterns?.insights ?? [];

	return (
		<div>
			<div className="flex items-center justify-between mb-3">
				<h2 className="flex items-center gap-2 text-foreground font-medium text-sm">
					<Sparkles className="w-3.5 h-3.5 text-accent/75" />
					Patterns
				</h2>
				<button
					onClick={() => refreshMutation.mutate()}
					disabled={refreshMutation.isPending}
					className={cn(
						"flex items-center gap-1 text-xs text-muted-foreground hover:text-accent transition-colors",
						refreshMutation.isPending && "animate-spin",
					)}
				>
					<RefreshCw className="w-3 h-3" />
					{refreshMutation.isPending ? "Analyzing..." : "Refresh"}
				</button>
			</div>

			{insights.length === 0 ? (
				<div className="rounded-lg border border-dashed border-border py-6 text-center text-muted-foreground/50 text-xs">
					{patterns
						? "No patterns detected yet — keep tracking!"
						: "Click Refresh to detect patterns in your data"}
				</div>
			) : (
				<div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
					{insights.map((card) => (
						<div
							key={card.id}
							className="rounded-lg border border-border/80 bg-card shadow-soft px-4 py-3 group relative"
						>
							<button
								onClick={() => dismissMutation.mutate(card.id)}
								className="absolute top-2 right-2 p-1 rounded text-muted-foreground/30 opacity-0 group-hover:opacity-100 hover:text-destructive transition-all"
							>
								<X className="w-3 h-3" />
							</button>
							<div className="flex items-start gap-2.5">
								<span className="text-base leading-none mt-0.5">
									{typeIcons[card.type] ?? "💡"}
								</span>
								<div className="min-w-0 flex-1">
									<p className="text-sm font-medium text-foreground">{card.title}</p>
									<p className="text-xs text-muted-foreground mt-1 leading-relaxed">{card.body}</p>
								</div>
							</div>
						</div>
					))}
				</div>
			)}
		</div>
	);
}
