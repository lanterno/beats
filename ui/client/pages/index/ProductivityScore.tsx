/**
 * ProductivityScore Component
 * Circular gauge (0-100) with component breakdown and 8-week sparkline.
 */

import { TrendingUp } from "lucide-react";
import { useState } from "react";
import { useProductivityScore, useScoreHistory } from "@/entities/intelligence";
import { cn } from "@/shared/lib";
import { Panel } from "@/shared/ui";

function ScoreRing({ score, size = 56 }: { score: number; size?: number }) {
	const strokeWidth = 4;
	const radius = (size - strokeWidth) / 2;
	const circumference = 2 * Math.PI * radius;
	const offset = circumference - (score / 100) * circumference;

	// Persimmon when the week is going badly, leaf when it is going well, the
	// muted ink between. There is no warning token: the middle band used to
	// name one and so drew no arc at all.
	const color =
		score < 40
			? "var(--color-destructive)"
			: score < 70
				? "var(--color-muted-foreground)"
				: "var(--color-success)";

	return (
		<svg width={size} height={size} className="shrink-0" aria-hidden="true" focusable="false">
			<circle
				cx={size / 2}
				cy={size / 2}
				r={radius}
				fill="none"
				stroke="var(--color-muted)"
				strokeWidth={strokeWidth}
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
				className="fill-foreground font-mono text-sm font-extrabold"
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
		<svg width={width} height={height} className="shrink-0" aria-hidden="true" focusable="false">
			<polyline
				points={points}
				fill="none"
				stroke="var(--color-muted-foreground)"
				strokeWidth={1.5}
				strokeLinecap="round"
				strokeLinejoin="round"
			/>
		</svg>
	);
}

const componentLabels: Record<string, string> = {
	consistency: "Consistency",
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
			<h2 className="flex items-center gap-2 px-2 mb-2.5 font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-foreground">
				<TrendingUp className="w-3.5 h-3.5 text-muted-foreground" />
				Productivity
			</h2>

			<Panel padding="p-0">
				<button
					type="button"
					onClick={() => setExpanded(!expanded)}
					className="w-full rounded-[1.625rem] px-6 py-4 text-left transition-colors hover:bg-secondary focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
				>
					<div className="flex items-center gap-4">
						<ScoreRing score={scoreData.score} />
						<div className="flex-1 min-w-0">
							<p className="text-xs font-medium text-muted-foreground">This week</p>
							<Sparkline data={sparklineData} />
						</div>
					</div>

					{expanded && (
						<div className="mt-3 pt-3 border-t border-border space-y-1.5">
							{Object.entries(scoreData.components).map(([key, value]) => (
								<div key={key} className="flex items-center gap-2">
									<span className="text-xs font-medium text-muted-foreground w-28">
										{componentLabels[key] ?? key}
									</span>
									<div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
										<div
											className={cn(
												"h-full rounded-full transition-all duration-500",
												value >= 20
													? "bg-success/70"
													: value >= 10
														? "bg-muted-foreground/60"
														: "bg-destructive",
											)}
											style={{ width: `${(value / 25) * 100}%` }}
										/>
									</div>
									<span className="text-xs font-mono font-bold text-muted-foreground w-6 text-right">
										{value}
									</span>
								</div>
							))}
						</div>
					)}
				</button>
			</Panel>
		</div>
	);
}
