/**
 * GoalRing Component
 * SVG radial arc showing weekly goal progress.
 */
import { cn } from "@/shared/lib";

interface GoalRingProps {
  /** Progress percentage 0-100+ */
  percent: number;
  /** Ring size in pixels */
  size?: number;
  /** Stroke width */
  strokeWidth?: number;
  /** Whether this is a cap (budget limit) vs target */
  isCap?: boolean;
  className?: string;
}

export function GoalRing({
  percent,
  size = 24,
  strokeWidth = 2.5,
  isCap = false,
  className,
}: GoalRingProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.min(percent, 100);
  const offset = circumference - (clamped / 100) * circumference;
  const isComplete = percent >= 100;
  const isOverBudget = isCap && percent >= 90;

  const trackColor = "hsl(var(--muted))";
  const fillColor = isCap
    ? isOverBudget
      ? "hsl(var(--destructive))"
      : "hsl(var(--accent) / 0.7)"
    : isComplete
      ? "hsl(var(--success))"
      : "hsl(var(--accent) / 0.8)";

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className={cn("shrink-0", className)}
    >
      {/* Track */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={trackColor}
        strokeWidth={strokeWidth}
      />
      {/* Progress arc */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={fillColor}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        className="transition-all duration-500 ease-out"
      />
      {/* Checkmark for complete */}
      {isComplete && !isCap && (
        <text
          x={size / 2}
          y={size / 2}
          textAnchor="middle"
          dominantBaseline="central"
          fill={fillColor}
          fontSize={size * 0.4}
          fontWeight="bold"
        >
          ✓
        </text>
      )}
    </svg>
  );
}
