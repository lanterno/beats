/**
 * MoodCorrelation Component
 * Shows mood trend and correlation with productivity.
 */

import { Heart } from "lucide-react";
import { useMoodCorrelation } from "@/entities/intelligence";

export function MoodCorrelation() {
	const { data: mood } = useMoodCorrelation();

	if (!mood || mood.mood_trend.length < 10) return null;

	const { correlation, high_mood_avg_hours, low_mood_avg_hours } = mood;

	return (
		<div className="rounded-lg border border-border/80 bg-card shadow-soft px-4 py-3">
			<h3 className="flex items-center gap-2 text-sm font-medium text-foreground mb-3">
				<Heart className="w-3.5 h-3.5 text-accent/75" />
				Mood & Productivity
			</h3>

			<div className="grid grid-cols-2 gap-3 text-center text-xs mb-3">
				<div className="rounded-md bg-secondary/30 px-3 py-2">
					<p className="text-muted-foreground">Good days (4+)</p>
					<p className="font-medium text-foreground text-lg tabular-nums">
						{high_mood_avg_hours.toFixed(1)}h
					</p>
				</div>
				<div className="rounded-md bg-secondary/30 px-3 py-2">
					<p className="text-muted-foreground">Tough days (&le;2)</p>
					<p className="font-medium text-foreground text-lg tabular-nums">
						{low_mood_avg_hours.toFixed(1)}h
					</p>
				</div>
			</div>

			<p className="text-xs text-muted-foreground">
				Correlation: <span className="font-medium text-foreground">{correlation.description}</span>{" "}
				(r = {correlation.r.toFixed(2)})
			</p>
		</div>
	);
}
