/**
 * CoachUsage — Settings panel showing LLM cost and cache stats.
 */

import { BarChart3, Sparkles } from "lucide-react";
import { useCoachUsage } from "@/entities/coach";
import { cn } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { HEADING, HEADING_ICON, LABEL } from "./styles";

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
			<h2 className={HEADING}>
				<Sparkles className={HEADING_ICON} />
				Coach Usage
			</h2>
			<Panel padding="p-5" className="space-y-4">
				{/* Budget bar */}
				<div>
					<div className="flex items-center justify-between gap-3 text-[12.5px] font-medium text-muted-foreground mb-1.5">
						<span>
							Month: ${month_total_usd.toFixed(2)} / ${budget_usd.toFixed(2)}
						</span>
						<span className="font-mono font-bold text-foreground">{budgetPct.toFixed(0)}%</span>
					</div>
					<div className="h-2 rounded-full bg-secondary overflow-hidden">
						<div
							className="h-full rounded-full bg-[hsl(var(--secondary))] transition-all"
							style={{ width: `${budgetPct}%` }}
						/>
					</div>
				</div>

				{/* Stats row */}
				<div className="grid grid-cols-3 gap-3 text-center">
					<div>
						<div className="font-heading text-[22px] font-extrabold tracking-[-0.02em] text-foreground">
							{totalCalls}
						</div>
						<div className="text-[11.5px] font-medium text-muted-foreground">Calls (30d)</div>
					</div>
					<div>
						<div className="font-heading text-[22px] font-extrabold tracking-[-0.02em] text-foreground">
							{cacheRatio}%
						</div>
						<div className="text-[11.5px] font-medium text-muted-foreground">Cache hit ratio</div>
					</div>
					<div>
						<div className="font-heading text-[22px] font-extrabold tracking-[-0.02em] text-foreground">
							${month_total_usd.toFixed(2)}
						</div>
						<div className="text-[11.5px] font-medium text-muted-foreground">Month cost</div>
					</div>
				</div>

				{/* Daily cost bars */}
				{days.length > 0 && (
					<div>
						<div className="flex items-center gap-1.5 mb-2">
							<BarChart3 className="w-3 h-3 text-muted-foreground" />
							<span className={cn(LABEL, "text-[10px]")}>Daily cost</span>
						</div>
						<div className="flex items-end gap-[2px] h-12">
							{days.slice(-30).map((d) => (
								<div
									key={d.date}
									className="flex-1 rounded-t-[3px] bg-[hsl(var(--secondary)/0.6)] hover:bg-[hsl(var(--secondary))] transition-colors"
									style={{
										height: `${Math.max(2, (d.cost_usd / maxCost) * 100)}%`,
									}}
									title={`${d.date}: $${d.cost_usd.toFixed(3)} (${d.calls} calls)`}
								/>
							))}
						</div>
					</div>
				)}
			</Panel>
		</section>
	);
}
