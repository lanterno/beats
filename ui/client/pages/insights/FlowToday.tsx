/**
 * FlowToday — surfaces today's flow windows from the daemon.
 *
 * Renders an SVG sparkline of the day's flow scores, the average score,
 * and a tap-to-inspect detail row that mirrors the companion's flow
 * inspector. Editor context (workspace + branch) appears when the
 * VS Code extension was sending heartbeats during that window.
 */
import { useMemo, useState } from "react";
import { useFlowWindows, useFlowWindowsLastDays } from "@/entities/session";
import { flowBaseline, shortRepoPath, summarizeFlow } from "@/shared/lib/flowAggregation";

const SPARK_W = 480;
const SPARK_H = 64;

export function FlowToday({
	projectId,
	editorRepo,
}: {
	projectId?: string;
	editorRepo?: string;
} = {}) {
	const filter = projectId || editorRepo ? { projectId, editorRepo } : undefined;
	const { data: windows, isLoading } = useFlowWindows(undefined, undefined, filter);
	// Baseline draws from the last 7 days (FlowThisWeek already issues this
	// fetch — react-query dedupes by key so this is free here). When a
	// project filter is active, the baseline filters too so "above typical"
	// is "above your typical day on THIS project".
	const { data: baselineWindows } = useFlowWindowsLastDays(7, filter);
	const [selectedIdx, setSelectedIdx] = useState<number | null>(null);

	const stats = useMemo(() => summarizeFlow(windows ?? []), [windows]);
	const baseline = useMemo(
		() => (baselineWindows ? flowBaseline(baselineWindows, new Date()) : null),
		[baselineWindows],
	);

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
					{stats && baseline !== null && <BaselineDelta avg={stats.avg} baseline={baseline} />}
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

			{stats && stats.count > 1 && (
				<div className="text-[11px] text-muted-foreground">
					peak at{" "}
					<button
						type="button"
						onClick={() => setSelectedIdx(stats.peakIndex)}
						className="text-accent hover:underline tabular-nums"
					>
						{formatTime(windows[stats.peakIndex].window_start)}
					</button>
				</div>
			)}

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
							{shortRepoPath(selected.editor_repo)}
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

/**
 * Renders today's avg compared to the user's recent baseline, color-coded.
 * Uses score points (e.g. "+5") rather than percentage of the baseline so a
 * day at 0.30 vs a 0.20 baseline doesn't read "+50%" — that framing
 * overstates the difference at low scores.
 *
 * Hidden when within ±3 score points of the baseline; that's small enough
 * to be noise on a typical day's window count and a flat "on track" badge
 * adds clutter without insight.
 */
function BaselineDelta({ avg, baseline }: { avg: number; baseline: number }) {
	const delta = Math.round((avg - baseline) * 100);
	if (Math.abs(delta) < 3) return null;
	const up = delta > 0;
	return (
		<span
			className={`tabular-nums ${up ? "text-green-500" : "text-amber-500"}`}
			title={`vs your 7-day baseline (${Math.round(baseline * 100)})`}
		>
			{up ? "↑" : "↓"} {Math.abs(delta)}
		</span>
	);
}
