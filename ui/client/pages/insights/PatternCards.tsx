/**
 * PatternCards Component
 * Grid of dismissible insight cards from pattern detection.
 */

import { RefreshCw, Sparkles, X } from "lucide-react";
import { useDismissPattern, usePatterns, useRefreshPatterns } from "@/entities/intelligence";
import { cn } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { LABEL, SKY_CHIP } from "./styles";

const typeIcons: Record<string, string> = {
	day_pattern: "📅",
	time_pattern: "⏰",
	stale_project: "💤",
	session_trend: "📊",
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
				<h2 className={cn(LABEL, "flex items-center gap-2 text-foreground")}>
					<Sparkles className="w-3.5 h-3.5" />
					Patterns
				</h2>
				<button
					type="button"
					onClick={() => refreshMutation.mutate()}
					disabled={refreshMutation.isPending}
					className={cn(SKY_CHIP, "inline-flex items-center gap-1 disabled:opacity-60")}
				>
					<RefreshCw className={cn("w-3 h-3", refreshMutation.isPending && "animate-spin")} />
					{refreshMutation.isPending ? "Analyzing..." : "Refresh"}
				</button>
			</div>

			{insights.length === 0 ? (
				<Panel
					padding="py-6 px-6"
					className="text-center text-muted-foreground font-medium text-xs"
				>
					{patterns
						? "No patterns detected yet — keep tracking!"
						: "Click Refresh to detect patterns in your data"}
				</Panel>
			) : (
				<div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
					{insights.map((card) => (
						<Panel key={card.id} padding="pl-5 pr-9 py-4" className="group relative">
							<button
								type="button"
								onClick={() => dismissMutation.mutate(card.id)}
								className="absolute top-2.5 right-2.5 grid place-items-center w-6 h-6 rounded-full text-muted-foreground hover:bg-secondary hover:text-foreground [@media(hover:hover)]:opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-all focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
							>
								<X className="w-3 h-3" />
							</button>
							<div className="flex items-start gap-2.5">
								<span className="text-base leading-none mt-0.5">
									{typeIcons[card.type] ?? "💡"}
								</span>
								<div className="min-w-0 flex-1">
									<p className="text-sm font-bold text-foreground">{card.title}</p>
									<p className="text-[12.5px] font-medium text-muted-foreground mt-1 leading-relaxed">
										{card.body}
									</p>
								</div>
							</div>
						</Panel>
					))}
				</div>
			)}
		</div>
	);
}
