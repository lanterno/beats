/**
 * CoachUsage — Settings panel showing LLM cost and cache stats.
 */

import { BarChart3, Sparkles } from "lucide-react";
import { useCoachUsage } from "@/entities/coach";

export function CoachUsage() {
	const { data, isLoading } = useCoachUsage();

	if (isLoading || !data) return null;

	const { days, month_total_usd, budget_usd } = data;
	const budgetPct = budget_usd > 0 ? Math.min(100, (month_total_usd / budget_usd) * 100) : 0;

	const totalCalls = days.reduce((s, d) => s + d.calls, 0);
	const totalCacheRead = days.reduce((s, d) => s + d.cache_read, 0);
	const totalInput = days.reduce((s, d) => s + d.input_tokens, 0);
	const cacheRatio = totalInput > 0 ? ((totalCacheRead / totalInput) * 100).toFixed(1) : "—";

	const maxCost = Math.max(...days.map((d) => d.cost_usd), 0.001);

	return (
		<section className="mb-8">
			<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
				<Sparkles className="w-4 h-4 text-accent" />
				Coach Usage
			</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-4">
				{/* Budget bar */}
				<div>
					<div className="flex items-center justify-between text-xs text-muted-foreground mb-1.5">
						<span>
							Month: ${month_total_usd.toFixed(2)} / ${budget_usd.toFixed(2)}
						</span>
						<span>{budgetPct.toFixed(0)}%</span>
					</div>
					<div className="h-2 rounded-full bg-secondary/40 overflow-hidden">
						<div
							className="h-full rounded-full bg-accent transition-all"
							style={{ width: `${budgetPct}%` }}
						/>
					</div>
				</div>

				{/* Stats row */}
				<div className="grid grid-cols-3 gap-3 text-center">
					<div>
						<div className="text-lg font-semibold text-foreground">{totalCalls}</div>
						<div className="text-[11px] text-muted-foreground">Calls (30d)</div>
					</div>
					<div>
						<div className="text-lg font-semibold text-foreground">{cacheRatio}%</div>
						<div className="text-[11px] text-muted-foreground">Cache hit ratio</div>
					</div>
					<div>
						<div className="text-lg font-semibold text-foreground">
							${month_total_usd.toFixed(2)}
						</div>
						<div className="text-[11px] text-muted-foreground">Month cost</div>
					</div>
				</div>

				{/* Daily cost bars */}
				{days.length > 0 && (
					<div>
						<div className="flex items-center gap-1.5 mb-2">
							<BarChart3 className="w-3 h-3 text-muted-foreground/60" />
							<span className="text-[11px] text-muted-foreground/60">Daily cost</span>
						</div>
						<div className="flex items-end gap-[2px] h-12">
							{days.slice(-30).map((d) => (
								<div
									key={d.date}
									className="flex-1 bg-accent/60 rounded-t-sm hover:bg-accent transition"
									style={{
										height: `${Math.max(2, (d.cost_usd / maxCost) * 100)}%`,
									}}
									title={`${d.date}: $${d.cost_usd.toFixed(3)} (${d.calls} calls)`}
								/>
							))}
						</div>
					</div>
				)}
			</div>
		</section>
	);
}
