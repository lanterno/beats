/**
 * BillingBudgetRow — one billing budget's reading: the sentence first, its
 * figures in the figures' face, then the meter running the row's width,
 * then what a money budget leaves out and what a running timer does to it.
 * The Clients page and the project's Billing panel both draw budgets with
 * it; each brings its own title and actions (a pencil, a remove) and, for
 * the unpriced hours, a link to where the rate is set.
 */

import type { ReactNode } from "react";
import { cn } from "@/shared/lib";
import { type BillingBudgetStatus, billingBudgetState, describeBillingBudget } from "../model";
import { BillingBudgetMeter } from "./BillingBudgetMeter";

export interface BillingBudgetRowProps {
	status: BillingBudgetStatus;
	/** The clock the running timer's instants are read against (`useNow`). */
	now: number;
	/** "Website", above the sentence; none on a panel that is already the scope's. */
	title?: string;
	/** Beside the title: the pencil, a remove. */
	actions?: ReactNode;
	/** After the unpriced hours: "Set its rate", where there is somewhere to set it. */
	unpricedAction?: ReactNode;
	className?: string;
}

/** The sentence with every figure — "€6,842.50", "40", "13:40" — in the figures' face. */
function withFigures(text: string): ReactNode[] {
	return text.split(/(\s+)/).map((token, i) => {
		if (!/\d/.test(token)) return token;
		const [, figure, after] = /^(.*?)([.,:;]?)$/.exec(token) ?? [token, token, ""];
		return (
			<span key={i}>
				<span className="font-mono font-bold">{figure}</span>
				{after}
			</span>
		);
	});
}

export function BillingBudgetRow({
	status,
	now,
	title,
	actions,
	unpricedAction,
	className,
}: BillingBudgetRowProps) {
	const words = describeBillingBudget(status, now);
	const state = billingBudgetState(status, now);
	const label = `${status.name}'s budget`;
	return (
		<div className={cn("min-w-0 text-[12.5px]", className)}>
			{(title || actions) && (
				<div className="flex items-center gap-x-2 gap-y-0.5 flex-wrap">
					{title && <span className="font-bold text-foreground min-w-0">{title}</span>}
					{actions && <span className="ml-auto inline-flex gap-0.5">{actions}</span>}
				</div>
			)}
			<p className="font-medium text-foreground leading-normal">{withFigures(words.sentence)}</p>
			{!status.upcoming && (
				<div className="mt-1.5">
					<BillingBudgetMeter
						percentUsed={status.percentUsed}
						warnAtPercent={status.warnAtPercent}
						state={state}
						label={label}
					/>
				</div>
			)}
			{words.unpriced && (
				<p className="mt-2 rounded-2xl bg-tint-sick px-3 py-1.5 font-medium text-tint-sick-ink">
					{words.unpriced} {unpricedAction}
				</p>
			)}
			{words.running && (
				<p
					className={cn(
						"mt-1.5 font-medium",
						state === "used_up" ? "text-destructive-ink" : "text-muted-foreground",
					)}
				>
					{withFigures(words.running)}
				</p>
			)}
		</div>
	);
}
