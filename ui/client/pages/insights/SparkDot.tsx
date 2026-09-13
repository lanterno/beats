/**
 * SparkDot — a marker on a sparkline that stays round.
 *
 * The flow sparklines stretch to their width (`preserveAspectRatio="none"`),
 * so an SVG circle draws as an ellipse. A near-zero-length stroke with a round
 * cap and a non-scaling stroke is a circle in screen pixels at any width; the
 * wider stroke under it is the panel, so the dot reads over the line.
 */
export function SparkDot({ x, y, className }: { x: number; y: number; className: string }) {
	const d = `M${x.toFixed(1)} ${y.toFixed(1)}h0.01`;
	return (
		<>
			<path
				d={d}
				className="stroke-card"
				strokeWidth={11}
				strokeLinecap="round"
				vectorEffect="non-scaling-stroke"
			/>
			<path
				d={d}
				className={className}
				strokeWidth={7}
				strokeLinecap="round"
				vectorEffect="non-scaling-stroke"
			/>
		</>
	);
}
