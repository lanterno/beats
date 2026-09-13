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
import { flowBaseline, shortRepoPath, summarizeFlow } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { SparkDot } from "./SparkDot";
import { AREA_BOTTOM, AREA_TOP, LABEL, LINKISH, META, SPARK_GRID } from "./styles";

const SPARK_W = 480;
const SPARK_H = 64;

export function FlowToday({
	projectId,
	editorRepo,
	editorLanguage,
	bundleId,
}: {
	projectId?: string;
	editorRepo?: string;
	editorLanguage?: string;
	bundleId?: string;
} = {}) {
	const filter =
		projectId || editorRepo || editorLanguage || bundleId
			? { projectId, editorRepo, editorLanguage, bundleId }
			: undefined;
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
			<Panel padding="px-6 py-[22px]">
				<p className={LABEL}>Flow today</p>
				<p className="mt-2 text-[12.5px] font-medium text-muted-foreground">
					No flow windows yet today. Make sure <code>beatsd run</code> is up.
				</p>
			</Panel>
		);
	}

	const selected =
		selectedIdx !== null && selectedIdx >= 0 && selectedIdx < windows.length
			? windows[selectedIdx]
			: null;

	return (
		<Panel padding="px-6 py-[22px]" className="space-y-3">
			<div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
				<p className={LABEL}>Flow today</p>
				<div className={`flex flex-wrap items-baseline gap-x-3 gap-y-1 ${META}`}>
					<span>
						avg{" "}
						<span className="text-foreground font-bold tabular-nums">
							{Math.round((stats?.avg ?? 0) * 100)}
						</span>
					</span>
					{stats && baseline !== null && <BaselineDelta avg={stats.avg} baseline={baseline} />}
					<span>
						peak{" "}
						<span className="text-foreground font-bold tabular-nums">
							{Math.round((stats?.peak ?? 0) * 100)}
						</span>
					</span>
					<span>
						<span className="text-foreground font-bold tabular-nums">{stats?.count ?? 0}</span>{" "}
						windows
					</span>
				</div>
			</div>

			<FlowSparkline windows={windows} selectedIdx={selectedIdx} onSelect={setSelectedIdx} />

			{stats && stats.count > 1 && (
				<div className={META}>
					peak at{" "}
					<button
						type="button"
						onClick={() => setSelectedIdx(stats.peakIndex)}
						className={`${LINKISH} tabular-nums`}
					>
						{formatTime(windows[stats.peakIndex].window_start)}
					</button>
				</div>
			)}

			{selected && (
				<div className="border-t border-border pt-2.5 space-y-1.5">
					<div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-medium text-muted-foreground">
						<span className="tabular-nums">{formatTime(selected.window_start)}</span>
						<span>
							<span className="text-foreground font-bold tabular-nums">
								{Math.round(selected.flow_score * 100)}
							</span>
							<span className="text-muted-foreground"> / 100</span>
						</span>
						{selected.dominant_category && (
							<span className="px-2 py-px rounded-full bg-secondary text-[10px] font-bold uppercase tracking-[0.06em]">
								{selected.dominant_category}
							</span>
						)}
						{selected.editor_repo && (
							<span className="text-foreground truncate max-w-[280px]" title={selected.editor_repo}>
								{shortRepoPath(selected.editor_repo)}
								{selected.editor_branch ? (
									<span className="text-muted-foreground"> · {selected.editor_branch}</span>
								) : null}
							</span>
						)}
					</div>
					{/* Why this window scored what it did: flow_score blends cadence,
					    coherence, and category fit; idle + context-switches flag
					    fragmentation. These were decoded but never shown. */}
					<div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
						<ScoreStat label="Cadence" value={Math.round(selected.cadence_score * 100)} />
						<ScoreStat label="Coherence" value={Math.round(selected.coherence_score * 100)} />
						<ScoreStat label="Fit" value={Math.round(selected.category_fit_score * 100)} />
						<ScoreStat label="Idle" value={`${Math.round(selected.idle_fraction * 100)}%`} />
						<ScoreStat label="Switches" value={selected.context_switches} />
					</div>
				</div>
			)}
		</Panel>
	);
}

/**
 * One labeled component of a flow window's score breakdown (e.g. "Cadence 72").
 */
function ScoreStat({ label, value }: { label: string; value: number | string }) {
	return (
		<span title={`${label}: ${value}`}>
			{label} <span className="text-foreground font-bold tabular-nums">{value}</span>
		</span>
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
	// Y is flipped because SVG origin is top-left.
	const yOf = (score: number) => SPARK_H - score * SPARK_H * 0.85;

	const points = windows.map((w, i) => {
		const x = n === 1 ? SPARK_W / 2 : (i / (n - 1)) * SPARK_W;
		return { x, y: yOf(w.flow_score) };
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
	const end = points[n - 1];

	return (
		<svg
			viewBox={`0 0 ${SPARK_W} ${SPARK_H}`}
			className="w-full h-16 cursor-crosshair overflow-visible"
			preserveAspectRatio="none"
			onMouseDown={handlePoint}
			onMouseMove={(e) => e.buttons === 1 && handlePoint(e)}
			onMouseLeave={() => {}}
		>
			<title>Flow score through the day</title>
			<defs>
				<linearGradient id="flow-area" x1="0" y1="0" x2="0" y2="1">
					<stop offset="0%" style={AREA_TOP} />
					<stop offset="100%" style={AREA_BOTTOM} />
				</linearGradient>
			</defs>
			{SPARK_GRID.map((v) => (
				<line
					key={v}
					x1={0}
					x2={SPARK_W}
					y1={yOf(v)}
					y2={yOf(v)}
					className="stroke-border"
					strokeWidth={1}
					vectorEffect="non-scaling-stroke"
				/>
			))}
			<path d={areaPath} fill="url(#flow-area)" />
			<path
				d={linePath}
				fill="none"
				className="stroke-success"
				strokeWidth={2}
				strokeLinejoin="round"
				strokeLinecap="round"
				vectorEffect="non-scaling-stroke"
			/>
			{sel && (
				<line
					x1={sel.x}
					y1={0}
					x2={sel.x}
					y2={SPARK_H}
					className="stroke-muted-foreground"
					strokeOpacity={0.5}
					strokeWidth={1}
					strokeDasharray="3 3"
					vectorEffect="non-scaling-stroke"
				/>
			)}
			{/* The latest window is today's newest: the accent marks it. */}
			<SparkDot x={end.x} y={end.y} className="stroke-accent" />
			{sel && sel !== end && <SparkDot x={sel.x} y={sel.y} className="stroke-success" />}
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
			className={`font-bold tabular-nums ${up ? "text-success-ink" : "text-destructive-ink"}`}
			title={`vs your 7-day baseline (${Math.round(baseline * 100)})`}
		>
			{up ? "↑" : "↓"} {Math.abs(delta)}
		</span>
	);
}
