/**
 * EstimationAccuracy Component
 * Shows planned vs actual comparison per project.
 */

import { Target } from "lucide-react";
import { useEstimationAccuracy } from "@/entities/intelligence";
import { cn } from "@/shared/lib";

export function EstimationAccuracy() {
	const { data: projects } = useEstimationAccuracy();

	if (!projects || projects.length === 0) return null;

	return (
		<div className="rounded-lg border border-border/80 bg-card shadow-soft px-4 py-3">
			<h3 className="flex items-center gap-2 text-sm font-medium text-foreground mb-3">
				<Target className="w-3.5 h-3.5 text-accent/75" />
				Estimation Accuracy
			</h3>

			<div className="space-y-2.5">
				{projects.map((p) => {
					const maxMin = Math.max(p.avg_planned_min, p.avg_actual_min, 1);
					return (
						<div key={p.project_id} className="text-xs">
							<div className="flex items-center justify-between mb-1">
								<span className="text-foreground font-medium truncate">{p.project_name}</span>
								<span
									className={cn(
										"tabular-nums font-medium",
										p.bias === "accurate"
											? "text-accent"
											: p.bias === "underestimate"
												? "text-warning"
												: "text-muted-foreground",
									)}
								>
									{p.accuracy_pct.toFixed(0)}%
								</span>
							</div>
							<div className="flex items-center gap-1.5">
								<span className="text-muted-foreground w-10 text-right">Plan</span>
								<div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
									<div
										className="h-full bg-muted-foreground/40 rounded-full"
										style={{ width: `${(p.avg_planned_min / maxMin) * 100}%` }}
									/>
								</div>
							</div>
							<div className="flex items-center gap-1.5 mt-0.5">
								<span className="text-muted-foreground w-10 text-right">Actual</span>
								<div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
									<div
										className="h-full bg-accent/60 rounded-full"
										style={{ width: `${(p.avg_actual_min / maxMin) * 100}%` }}
									/>
								</div>
							</div>
						</div>
					);
				})}
			</div>
		</div>
	);
}
