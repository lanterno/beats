/**
 * EmptyState — animated SVG empty states for various contexts.
 */

interface EmptyStateProps {
	variant: "clock" | "seedling" | "chart";
	message: string;
}

export function EmptyState({ variant, message }: EmptyStateProps) {
	return (
		<div className="flex flex-col items-center justify-center py-12 gap-3">
			<div className="w-16 h-16 text-muted-foreground/20">
				{variant === "clock" && <PulsingClock />}
				{variant === "seedling" && <SproutingSeedling />}
				{variant === "chart" && <GrowingChart />}
			</div>
			<p className="text-xs text-muted-foreground/50 text-center max-w-[200px]">{message}</p>
		</div>
	);
}

function PulsingClock() {
	return (
		<svg viewBox="0 0 64 64" fill="none" className="w-full h-full">
			<circle cx="32" cy="32" r="28" stroke="currentColor" strokeWidth="2" opacity="0.4">
				<animate attributeName="r" values="26;28;26" dur="3s" repeatCount="indefinite" />
				<animate attributeName="opacity" values="0.3;0.5;0.3" dur="3s" repeatCount="indefinite" />
			</circle>
			<circle cx="32" cy="32" r="2" fill="currentColor" opacity="0.5" />
			{/* Minute hand */}
			<line
				x1="32"
				y1="32"
				x2="32"
				y2="16"
				stroke="currentColor"
				strokeWidth="2"
				strokeLinecap="round"
				opacity="0.4"
			>
				<animateTransform
					attributeName="transform"
					type="rotate"
					from="0 32 32"
					to="360 32 32"
					dur="8s"
					repeatCount="indefinite"
				/>
			</line>
			{/* Hour hand */}
			<line
				x1="32"
				y1="32"
				x2="32"
				y2="22"
				stroke="currentColor"
				strokeWidth="2.5"
				strokeLinecap="round"
				opacity="0.3"
			>
				<animateTransform
					attributeName="transform"
					type="rotate"
					from="0 32 32"
					to="360 32 32"
					dur="48s"
					repeatCount="indefinite"
				/>
			</line>
		</svg>
	);
}

function SproutingSeedling() {
	return (
		<svg viewBox="0 0 64 64" fill="none" className="w-full h-full">
			{/* Ground line */}
			<line
				x1="16"
				y1="52"
				x2="48"
				y2="52"
				stroke="currentColor"
				strokeWidth="2"
				opacity="0.2"
				strokeLinecap="round"
			/>
			{/* Stem */}
			<line
				x1="32"
				y1="52"
				x2="32"
				y2="28"
				stroke="currentColor"
				strokeWidth="2"
				strokeLinecap="round"
				opacity="0.3"
			>
				<animate attributeName="y2" values="52;28;52" dur="4s" repeatCount="indefinite" />
				<animate attributeName="opacity" values="0;0.4;0" dur="4s" repeatCount="indefinite" />
			</line>
			{/* Left leaf */}
			<path
				d="M32 36 C28 32, 22 32, 20 28"
				stroke="currentColor"
				strokeWidth="2"
				strokeLinecap="round"
				fill="none"
				opacity="0.3"
			>
				<animate attributeName="opacity" values="0;0.3;0" dur="4s" repeatCount="indefinite" />
			</path>
			{/* Right leaf */}
			<path
				d="M32 32 C36 28, 42 28, 44 24"
				stroke="currentColor"
				strokeWidth="2"
				strokeLinecap="round"
				fill="none"
				opacity="0.3"
			>
				<animate
					attributeName="opacity"
					values="0;0.3;0"
					dur="4s"
					repeatCount="indefinite"
					begin="0.5s"
				/>
			</path>
		</svg>
	);
}

function GrowingChart() {
	return (
		<svg viewBox="0 0 64 64" fill="none" className="w-full h-full">
			{/* Base line */}
			<line
				x1="12"
				y1="52"
				x2="52"
				y2="52"
				stroke="currentColor"
				strokeWidth="2"
				opacity="0.2"
				strokeLinecap="round"
			/>
			{/* Bars growing upward */}
			{[0, 1, 2, 3, 4].map((i) => {
				const x = 16 + i * 8;
				const heights = [12, 24, 18, 30, 20];
				return (
					<rect
						key={i}
						x={x}
						y={52 - heights[i]}
						width="4"
						rx="1"
						fill="currentColor"
						opacity="0.25"
					>
						<animate
							attributeName="height"
							values={`0;${heights[i]};0`}
							dur="3s"
							begin={`${i * 0.2}s`}
							repeatCount="indefinite"
						/>
						<animate
							attributeName="y"
							values={`52;${52 - heights[i]};52`}
							dur="3s"
							begin={`${i * 0.2}s`}
							repeatCount="indefinite"
						/>
					</rect>
				);
			})}
		</svg>
	);
}
