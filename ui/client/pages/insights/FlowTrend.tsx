/**
 * FlowTrend — last 12 weeks of avg flow score as a line+area sparkline.
 * Answers a question the other Flow* cards don't: "is my flow trending
 * up or down over the past quarter?" Different time scale than
 * FlowThisWeek (7 days) or FlowRhythm (hour-of-day).
 *
 * Renders nothing when fewer than 4 weeks have data — a 12-week trend
 * line drawn from 1 week of history would be misleading.
 *
 * Hovers on the SVG select a week and pin the score in a small detail
 * row beneath the chart, mirroring the FlowToday inspector pattern.
 */
import { useMemo, useState } from "react";
import { useWeeklyFlowTrend } from "@/entities/session";
import { Panel } from "@/shared/ui";
import { SparkDot } from "./SparkDot";
import { AREA_BOTTOM, AREA_TOP, LABEL, META, SPARK_GRID } from "./styles";

const WEEKS = 12;
const MIN_WEEKS_TO_RENDER = 4;
const W = 480;
const H = 64;

export function FlowTrend({
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
	const { data: points, isLoading } = useWeeklyFlowTrend(WEEKS, filter);
	const [selectedIdx, setSelectedIdx] = useState<number | null>(null);

	const populated = useMemo(() => (points ?? []).filter((p) => p.count > 0), [points]);

	if (isLoading) return null;
	if (!points || populated.length < MIN_WEEKS_TO_RENDER) return null;

	const last = populated[populated.length - 1];
	const first = populated[0];
	const delta = Math.round((last.avg - first.avg) * 100);

	const selected = selectedIdx !== null && points[selectedIdx] ? points[selectedIdx] : null;

	return (
		<Panel padding="px-6 py-[22px]" className="space-y-3">
			<div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
				<p className={LABEL}>Flow trend</p>
				<div className={`flex items-baseline gap-3 ${META}`}>
					<span>last {WEEKS} weeks</span>
					{populated.length >= 2 && <TrendDelta delta={delta} />}
				</div>
			</div>

			<TrendSparkline points={points} selectedIdx={selectedIdx} onSelect={setSelectedIdx} />

			{selected && selected.count > 0 && (
				<div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-medium text-muted-foreground border-t border-border pt-2.5">
					<span className="tabular-nums">week of {formatWeek(selected.weekStart)}</span>
					<span>
						<span className="text-foreground font-bold tabular-nums">
							{Math.round(selected.avg * 100)}
						</span>
						<span className="text-muted-foreground"> / 100</span>
					</span>
					<span>
						<span className="text-foreground font-bold tabular-nums">{selected.count}</span> windows
					</span>
				</div>
			)}
		</Panel>
	);
}

interface SparklineProps {
	points: { weekStart: string; avg: number; count: number }[];
	selectedIdx: number | null;
	onSelect: (idx: number | null) => void;
}

function TrendSparkline({ points, selectedIdx, onSelect }: SparklineProps) {
	const n = points.length;
	if (n === 0) return null;

	// Empty weeks (count=0) get a y of 0 — visible as a dip-to-floor.
	// That's correct: the user actually had no flow that week.
	const yOf = (score: number) => H - score * H * 0.85;
	const xy = points.map((p, i) => {
		const x = n === 1 ? W / 2 : (i / (n - 1)) * W;
		return { x, y: yOf(p.avg) };
	});

	const linePath = xy
		.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
		.join(" ");
	const areaPath = `${linePath} L${W} ${H} L0 ${H} Z`;

	const handlePoint = (e: React.MouseEvent<SVGSVGElement>) => {
		const rect = e.currentTarget.getBoundingClientRect();
		const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
		const idx = n === 1 ? 0 : Math.round(ratio * (n - 1));
		onSelect(idx);
	};

	const sel = selectedIdx !== null && selectedIdx >= 0 && selectedIdx < n ? xy[selectedIdx] : null;
	const end = xy[n - 1];

	return (
		<svg
			viewBox={`0 0 ${W} ${H}`}
			className="w-full h-16 cursor-crosshair overflow-visible"
			preserveAspectRatio="none"
			onMouseDown={handlePoint}
			onMouseMove={(e) => e.buttons === 1 && handlePoint(e)}
		>
			<title>Flow score trend</title>
			<defs>
				<linearGradient id="trend-area" x1="0" y1="0" x2="0" y2="1">
					<stop offset="0%" style={AREA_TOP} />
					<stop offset="100%" style={AREA_BOTTOM} />
				</linearGradient>
			</defs>
			{SPARK_GRID.map((v) => (
				<line
					key={v}
					x1={0}
					x2={W}
					y1={yOf(v)}
					y2={yOf(v)}
					className="stroke-border"
					strokeWidth={1}
					vectorEffect="non-scaling-stroke"
				/>
			))}
			<path d={areaPath} fill="url(#trend-area)" />
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
					y2={H}
					className="stroke-muted-foreground"
					strokeOpacity={0.5}
					strokeWidth={1}
					strokeDasharray="3 3"
					vectorEffect="non-scaling-stroke"
				/>
			)}
			{/* This week, the line's end. */}
			<SparkDot x={end.x} y={end.y} className="stroke-success" />
			{sel && sel !== end && <SparkDot x={sel.x} y={sel.y} className="stroke-success" />}
		</svg>
	);
}

/** Score-points delta vs the first populated week. Hidden when within
 * ±3 — same threshold FlowToday's BaselineDelta uses, since 12 weekly
 * means are noisy below that. */
function TrendDelta({ delta }: { delta: number }) {
	if (Math.abs(delta) < 3) return null;
	const up = delta > 0;
	return (
		<span
			className={`font-bold tabular-nums ${up ? "text-success-ink" : "text-destructive-ink"}`}
			title="vs the first week in the trend"
		>
			{up ? "↑" : "↓"} {Math.abs(delta)}
		</span>
	);
}

function formatWeek(yyyymmdd: string): string {
	const [y, m, d] = yyyymmdd.split("-").map(Number);
	const date = new Date(y, m - 1, d);
	return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
