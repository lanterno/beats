/**
 * BillingBudgetMeter — how much of a billing budget is used: a thin bar to
 * `percentUsed`, capped at the end, with a tick at the warning. The fill is
 * the sun while under, the persimmon fill once near, and its ink once used
 * up. The sentence always sits beside it, so the colour is never the only
 * signal.
 */

import { cn } from "@/shared/lib";
import type { BillingBudgetState } from "../model";

export interface BillingBudgetMeterProps {
	/** The API's `percent_used`: rounded down, not capped. */
	percentUsed: number;
	warnAtPercent: number;
	/** The state to draw, lifted by a running timer's crossing (`billingBudgetState`). */
	state: BillingBudgetState;
	/** "Studio Kite's budget". */
	label: string;
}

const FILL: Record<BillingBudgetState, string> = {
	under: "bg-accent",
	near: "bg-destructive",
	used_up: "bg-destructive-ink",
};

export function BillingBudgetMeter({
	percentUsed,
	warnAtPercent,
	state,
	label,
}: BillingBudgetMeterProps) {
	// A running timer's crossing lifts the state before the figures move, so
	// the bar runs full and the meter says so: the percent is from before it.
	const lifted = state === "used_up" && percentUsed < 100;
	const value = lifted ? 100 : Math.max(0, Math.min(percentUsed, 100));
	const width = state === "used_up" ? 100 : value;
	return (
		// biome-ignore lint/a11y/useSemanticElements: a native <meter> draws its own bar, which takes neither the warning's tick nor the theme's fills.
		<div
			role="meter"
			aria-label={label}
			aria-valuemin={0}
			aria-valuemax={100}
			aria-valuenow={value}
			aria-valuetext={lifted ? "Used up by the running timer" : `${percentUsed}% used`}
			className="relative h-1.5 w-full rounded-full bg-muted"
		>
			<div
				className={cn("h-full rounded-full transition-[width]", FILL[state])}
				style={{ width: `${width}%` }}
			/>
			<span
				aria-hidden="true"
				className="absolute -top-0.5 -bottom-0.5 w-0.5 -ml-px rounded-full bg-foreground/35"
				style={{ left: `${warnAtPercent}%` }}
			/>
		</div>
	);
}
