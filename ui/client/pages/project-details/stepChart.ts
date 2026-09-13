/**
 * The register's step chart as geometry — the mockup's `stepChart`
 * (docs/project-page-mockup.html), pure so it can be pinned without a DOM:
 * hours per week as a step function over a contract's life (or a goal's),
 * solid through today and dashed after it, the area under the solid part,
 * each step labelled under its own line, the dates under the axis.
 *
 * x runs from the first step to `endedOn` when the contract ended, else to
 * the later of today + 3 months and the last step + 6 months, so a planned
 * term always has room to show. A step of `null` hours (an objective term,
 * a "no goal" override) is a labelled gap: no line, no riser into or out of
 * it, no area. A step at 0 is a line on the axis.
 *
 * Where steps crowd, the step in force — the one the today line crosses —
 * keeps its label and its date, and a neighbour too close gives up its own.
 */

import { formatDateShort, parseIsoDate } from "@/shared/lib";

export interface ChartStep {
	/** The day the step takes effect, YYYY-MM-DD. */
	date: string;
	/** Hours per week; null for a stretch that owes none — drawn as a gap. */
	hours: number | null;
	/** Written under the step's line: "80% · 33.6 h". */
	label: string;
}

export interface ChartSegment {
	x1: number;
	y1: number;
	x2: number;
	y2: number;
	kind: "solid" | "dashed";
}

export interface ChartText {
	x: number;
	y: number;
	text: string;
	anchor: "start" | "middle" | "end";
}

export interface StepChartGeometry {
	width: number;
	height: number;
	/** The y of the axis (0 h). */
	baseline: number;
	/** The y of a faint rule at 0 and at each step's hours. */
	grid: number[];
	/** Horizontal lines and risers, in drawing order. */
	segments: ChartSegment[];
	/** One closed path per run of solid steps: the meadow under the line. */
	areas: string[];
	/** Today's marker; null when today is outside the chart. */
	today: { x: number; top: number } | null;
	labels: ChartText[];
	axis: ChartText[];
}

export const CHART_WIDTH = 296;
export const CHART_HEIGHT = 112;
const PAD_LEFT = 4;
const PAD_RIGHT = 4;
const PAD_TOP = 18;
const PAD_BOTTOM = 24;
/**
 * A step narrower than this keeps its line but not its label (the term list
 * names it) — unless it is in force; a label this close after the one before
 * is dropped too.
 */
const MIN_LABEL_WIDTH = 40;
/** Axis dates closer than this to the one before are left out rather than overprinted. */
const MIN_AXIS_GAP = 36;

function round(n: number): number {
	return Math.round(n * 100) / 100;
}

/** Whole days since the epoch, on the calendar — no clock, so no DST. */
function dayNumber(iso: string): number {
	const [y, m, d] = iso.split("-").map(Number);
	return Date.UTC(y, m - 1, d) / 86_400_000;
}

function addMonths(iso: string, months: number): string {
	const d = parseIsoDate(iso) ?? new Date(0);
	d.setMonth(d.getMonth() + months);
	return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** "Jan 5 ’26" — the year only where it changes from the date before. */
function axisDate(iso: string, withYear: boolean): string {
	const d = parseIsoDate(iso) ?? new Date(0);
	const base = formatDateShort(d);
	return withYear ? `${base} ’${String(d.getFullYear()).slice(2)}` : base;
}

export function stepChartGeometry(input: {
	steps: ChartStep[];
	todayIso: string;
	endedOn?: string;
}): StepChartGeometry | null {
	const { todayIso, endedOn } = input;
	const sorted = [...input.steps].sort((a, b) => a.date.localeCompare(b.date));
	if (sorted.length === 0) return null;
	const first = sorted[0].date;
	const last = sorted[sorted.length - 1].date;
	const later =
		addMonths(todayIso, 3) > addMonths(last, 6) ? addMonths(todayIso, 3) : addMonths(last, 6);
	const end = endedOn ?? later;
	// A step dated after the contract ended never took effect.
	const steps = sorted.filter((s) => s.date <= end);
	if (steps.length === 0) return null;

	const t0 = dayNumber(first);
	const t1 = Math.max(dayNumber(end), t0 + 1);
	const max = Math.max(0, ...steps.map((s) => s.hours ?? 0)) || 1;
	const x = (iso: string) =>
		PAD_LEFT +
		((Math.min(dayNumber(iso), t1) - t0) / (t1 - t0)) * (CHART_WIDTH - PAD_LEFT - PAD_RIGHT);
	const y = (hours: number) => PAD_TOP + (1 - hours / max) * (CHART_HEIGHT - PAD_TOP - PAD_BOTTOM);
	const baseline = round(y(0));
	// Solid through today, or through the end when the contract is over.
	const cutIso = todayIso < end ? todayIso : end;
	const cut = x(cutIso);

	const segments: ChartSegment[] = [];
	const areas: string[] = [];
	const labels: ChartText[] = [];
	const axis: ChartText[] = [];
	let run: [number, number][] = [];
	const closeRun = () => {
		if (run.length >= 2 && run[run.length - 1][0] > run[0][0]) {
			const points = run.map(([px, py]) => `L${round(px)},${round(py)}`).join("");
			areas.push(
				`M${round(run[0][0])},${baseline}${points}L${round(run[run.length - 1][0])},${baseline}Z`,
			);
		}
		run = [];
	};
	const push = (x1: number, y1: number, x2: number, y2: number, kind: ChartSegment["kind"]) => {
		segments.push({ x1: round(x1), y1: round(y1), x2: round(x2), y2: round(y2), kind });
	};

	const axisYears: number[] = [];
	let inForceIndex = -1;
	steps.forEach((step, i) => {
		if (step.date <= cutIso) inForceIndex = i;
	});

	steps.forEach((step, i) => {
		const inForce = i === inForceIndex;
		const next = steps[i + 1];
		const segEnd = next ? next.date : end;
		const xs = x(step.date);
		const xe = x(segEnd);

		if (step.hours === null) {
			closeRun();
		} else {
			const yy = y(step.hours);
			if (step.date > cutIso) {
				// A step still to come, dashed from its first day.
				push(xs, yy, xe, yy, "dashed");
			} else if (segEnd <= cutIso) {
				push(xs, yy, xe, yy, "solid");
				run.push([xs, yy], [xe, yy]);
			} else {
				if (cut > xs) {
					push(xs, yy, cut, yy, "solid");
					run.push([xs, yy], [cut, yy]);
				}
				push(Math.max(xs, cut), yy, xe, yy, "dashed");
			}
			if (next && next.hours !== null && next.hours !== step.hours) {
				const solid = next.date <= cutIso;
				push(xe, yy, xe, y(next.hours), solid ? "solid" : "dashed");
			}
			if (!(next && next.hours !== null && next.date <= cutIso)) closeRun();
		}

		const lastLabel = labels[labels.length - 1];
		const crowded = lastLabel !== undefined && xs + 4 - lastLabel.x < MIN_LABEL_WIDTH;
		if ((xe - xs >= MIN_LABEL_WIDTH || inForce) && !crowded) {
			const onAxis = step.hours === null || step.hours === 0;
			labels.push({
				x: round(xs + 4),
				y: round(onAxis ? baseline - 5 : y(step.hours ?? 0) + 12),
				text: step.label,
				anchor: "start",
			});
		}

		let lastAxis = axis[axis.length - 1];
		if (lastAxis && xs - lastAxis.x < MIN_AXIS_GAP && inForce && axis.length > 1) {
			// The day the step in force began outranks the date before it.
			axis.pop();
			axisYears.pop();
			lastAxis = axis[axis.length - 1];
		}
		if (!lastAxis || xs - lastAxis.x >= MIN_AXIS_GAP) {
			const year = Number(step.date.slice(0, 4));
			const lastYear = axisYears[axisYears.length - 1];
			const anchor = i === 0 ? "start" : xs > CHART_WIDTH - 44 ? "end" : "middle";
			axis.push({
				x: round(xs),
				y: CHART_HEIGHT - 7,
				text: axisDate(step.date, lastYear === undefined || year !== lastYear),
				anchor,
			});
			axisYears.push(year);
		}
	});
	closeRun();

	const grid = [...new Set([0, ...steps.map((s) => s.hours ?? 0)])].map((h) => round(y(h)));
	const today =
		todayIso >= first && todayIso <= end ? { x: round(x(todayIso)), top: PAD_TOP } : null;

	return {
		width: CHART_WIDTH,
		height: CHART_HEIGHT,
		baseline,
		grid,
		segments,
		areas,
		today,
		labels,
		axis,
	};
}
