/**
 * FlowToday — surfaces today's flow windows from the daemon.
 *
 * Renders an SVG sparkline of the day's flow scores, the average score,
 * and a tap-to-inspect detail row that mirrors the companion's flow
 * inspector. Editor context (workspace + branch) appears when the
 * VS Code extension was sending heartbeats during that window.
 */
import { useMemo, useState } from "react";
import { useFlowWindows } from "@/entities/session";

const SPARK_W = 480;
const SPARK_H = 64;

export function FlowToday() {
	const { data: windows, isLoading } = useFlowWindows();
	const [selectedIdx, setSelectedIdx] = useState<number | null>(null);

	const stats = useMemo(() => {
		if (!windows || windows.length === 0) return null;
		const scores = windows.map((w) => w.flow_score);
		const avg = scores.reduce((s, v) => s + v, 0) / scores.length;
		const peak = Math.max(...scores);
		return { avg, peak, count: windows.length };
	}, [windows]);

	if (isLoading) return null;
	if (!windows || windows.length === 0) {
		return (
			<div className="rounded-lg border border-border/60 bg-secondary/20 px-4 py-3">
				<p className="font-heading text-sm text-foreground mb-1">Flow today</p>
				<p className="text-muted-foreground text-xs">
					No flow windows yet today. Make sure <code>beatsd run</code> is up.
				</p>
			</div>
		);
	}

	const selected =
		selectedIdx !== null && selectedIdx >= 0 && selectedIdx < windows.length
			? windows[selectedIdx]
			: null;

	return (
		<div className="rounded-lg border border-border/60 bg-secondary/20 px-4 py-3 space-y-3">
			<div className="flex items-baseline justify-between">
				<p className="font-heading text-sm text-foreground">Flow today</p>
				<div className="flex items-baseline gap-3 text-[11px] text-muted-foreground">
					<span>
						avg{" "}
						<span className="text-foreground tabular-nums">
							{Math.round((stats?.avg ?? 0) * 100)}
						</span>
					</span>
					<span>
						peak{" "}
						<span className="text-foreground tabular-nums">
							{Math.round((stats?.peak ?? 0) * 100)}
						</span>
					</span>
					<span>
						<span className="text-foreground tabular-nums">{stats?.count ?? 0}</span> windows
					</span>
				</div>
			</div>

			<FlowSparkline windows={windows} selectedIdx={selectedIdx} onSelect={setSelectedIdx} />

			{selected && (
				<div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground border-t border-border/40 pt-2">
					<span className="tabular-nums">{formatTime(selected.window_start)}</span>
					<span>
						<span className="text-foreground tabular-nums">
							{Math.round(selected.flow_score * 100)}
						</span>
						<span className="text-muted-foreground"> / 100</span>
					</span>
					{selected.dominant_category && (
						<span className="uppercase tracking-wider text-[9px]">
							{selected.dominant_category}
						</span>
					)}
					{selected.editor_repo && (
						<span
							className="text-foreground/70 truncate max-w-[280px]"
							title={selected.editor_repo}
						>
							{shortRepo(selected.editor_repo)}
							{selected.editor_branch ? (
								<span className="text-muted-foreground"> · {selected.editor_branch}</span>
							) : null}
						</span>
					)}
				</div>
			)}
		</div>
	);
}

interface SparklineProps {
	windows: ReturnType<typeof useFlowWindows>["data"];
	selectedIdx: number | null;
	onSelect: (idx: number | null) => void;
}

function FlowSparkline({ windows, selectedIdx, onSelect }: SparklineProps) {
	if (!windows || windows.length === 0) return null;
	const n = windows.length;

	// Build the area path. Y is flipped because SVG origin is top-left.
	const points = windows.map((w, i) => {
		const x = n === 1 ? SPARK_W / 2 : (i / (n - 1)) * SPARK_W;
		const y = SPARK_H - w.flow_score * SPARK_H * 0.85;
		return { x, y };
	});

	const linePath = points
		.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
		.join(" ");
	const areaPath = `${linePath} L${SPARK_W} ${SPARK_H} L0 ${SPARK_H} Z`;

	const handlePoint = (e: React.MouseEvent<SVGSVGElement>) => {
		const rect = e.currentTarget.getBoundingClientRect();
		const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
		const idx = n === 1 ? 0 : Math.round(ratio * (n - 1));
		onSelect(idx);
	};

	const sel =
		selectedIdx !== null && selectedIdx >= 0 && selectedIdx < n ? points[selectedIdx] : null;

	return (
		<svg
			viewBox={`0 0 ${SPARK_W} ${SPARK_H}`}
			className="w-full h-16 cursor-crosshair"
			preserveAspectRatio="none"
			onMouseDown={handlePoint}
			onMouseMove={(e) => e.buttons === 1 && handlePoint(e)}
			onMouseLeave={() => {}}
		>
			<defs>
				<linearGradient id="flow-area" x1="0" y1="0" x2="0" y2="1">
					<stop offset="0%" stopColor="rgb(var(--accent-rgb, 212 149 42))" stopOpacity="0.25" />
					<stop offset="100%" stopColor="rgb(var(--accent-rgb, 212 149 42))" stopOpacity="0" />
				</linearGradient>
			</defs>
			<path d={areaPath} fill="url(#flow-area)" />
			<path
				d={linePath}
				fill="none"
				stroke="rgb(var(--accent-rgb, 212 149 42))"
				strokeWidth="1.5"
				strokeLinecap="round"
				vectorEffect="non-scaling-stroke"
			/>
			{sel && (
				<>
					<line
						x1={sel.x}
						y1={0}
						x2={sel.x}
						y2={SPARK_H}
						stroke="rgb(var(--accent-rgb, 212 149 42))"
						strokeOpacity="0.35"
						strokeWidth="1"
						vectorEffect="non-scaling-stroke"
					/>
					<circle
						cx={sel.x}
						cy={sel.y}
						r="3.5"
						fill="rgb(var(--accent-rgb, 212 149 42))"
						stroke="rgb(var(--background-rgb, 26 20 8))"
						strokeWidth="1.5"
					/>
				</>
			)}
		</svg>
	);
}

function formatTime(iso: string): string {
	const d = new Date(iso);
	return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function shortRepo(path: string): string {
	const parts = path.split(/[\\/]/);
	const tail = parts.filter(Boolean).slice(-2).join("/");
	return tail || path;
}
