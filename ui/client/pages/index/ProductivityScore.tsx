/**
 * ProductivityScore Component
 * Circular gauge (0-100) with component breakdown and 8-week sparkline.
 */

import { TrendingUp } from "lucide-react";
import { useState } from "react";
import { useProductivityScore, useScoreHistory } from "@/entities/intelligence";
import { cn } from "@/shared/lib";

function ScoreRing({ score, size = 56 }: { score: number; size?: number }) {
	const strokeWidth = 4;
	const radius = (size - strokeWidth) / 2;
	const circumference = 2 * Math.PI * radius;
	const offset = circumference - (score / 100) * circumference;

	const color =
		score < 40
			? "var(--color-destructive)"
			: score < 70
				? "var(--color-warning)"
				: "var(--color-accent)";

	return (
		<svg width={size} height={size} className="shrink-0">
			<circle
				cx={size / 2}
				cy={size / 2}
				r={radius}
				fill="none"
				stroke="currentColor"
				strokeWidth={strokeWidth}
				className="text-border/50"
			/>
			<circle
				cx={size / 2}
				cy={size / 2}
				r={radius}
				fill="none"
				stroke={color}
				strokeWidth={strokeWidth}
				strokeDasharray={circumference}
				strokeDashoffset={offset}
				strokeLinecap="round"
				transform={`rotate(-90 ${size / 2} ${size / 2})`}
				className="transition-all duration-700"
			/>
			<text
				x={size / 2}
				y={size / 2}
				textAnchor="middle"
				dominantBaseline="central"
				className="fill-foreground text-sm font-semibold tabular-nums"
			>
				{score}
			</text>
		</svg>
	);
}

function Sparkline({
	data,
	width = 100,
	height = 24,
}: {
	data: number[];
	width?: number;
	height?: number;
}) {
	if (data.length < 2) return null;

	const max = Math.max(...data, 1);
	const min = Math.min(...data, 0);
	const range = max - min || 1;

	const points = data
		.map((v, i) => {
			const x = (i / (data.length - 1)) * width;
			const y = height - ((v - min) / range) * (height - 4) - 2;
			return `${x},${y}`;
		})
		.join(" ");

	return (
		<svg width={width} height={height} className="shrink-0">
			<polyline
				points={points}
				fill="none"
				stroke="var(--color-accent)"
				strokeWidth={1.5}
				strokeLinecap="round"
				strokeLinejoin="round"
				className="opacity-60"
			/>
		</svg>
	);
}

const componentLabels: Record<string, string> = {
	consistency: "Consistency",
	intentions: "Intentions",
	goals: "Goal progress",
	quality: "Session quality",
};

export function ProductivityScore() {
	const { data: scoreData } = useProductivityScore();
	const { data: history } = useScoreHistory(8);
	const [expanded, setExpanded] = useState(false);

	if (!scoreData) return null;

	const sparklineData = (history ?? []).map((h) => h.score);

	return (
		<div>
			<h2 className="flex items-center gap-2 text-foreground font-medium text-sm mb-3">
				<TrendingUp className="w-3.5 h-3.5 text-accent/75" />
				Productivity
			</h2>

			<button
				onClick={() => setExpanded(!expanded)}
				className="w-full rounded-lg border border-border/80 bg-card shadow-soft px-4 py-3 text-left transition-colors hover:bg-secondary/20"
			>
				<div className="flex items-center gap-4">
					<ScoreRing score={scoreData.score} />
					<div className="flex-1 min-w-0">
						<p className="text-xs text-muted-foreground">This week</p>
						<Sparkline data={sparklineData} />
					</div>
				</div>

				{expanded && (
					<div className="mt-3 pt-3 border-t border-border/40 space-y-1.5">
						{Object.entries(scoreData.components).map(([key, value]) => (
							<div key={key} className="flex items-center gap-2">
								<span className="text-xs text-muted-foreground w-28">
									{componentLabels[key] ?? key}
								</span>
								<div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
									<div
										className={cn(
											"h-full rounded-full transition-all duration-500",
											value >= 20 ? "bg-accent" : value >= 10 ? "bg-warning" : "bg-destructive/60",
										)}
										style={{ width: `${(value / 25) * 100}%` }}
									/>
								</div>
								<span className="text-xs tabular-nums text-muted-foreground w-6 text-right">
									{value}
								</span>
							</div>
						))}
					</div>
				)}
			</button>
		</div>
	);
}
