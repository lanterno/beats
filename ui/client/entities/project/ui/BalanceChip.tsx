/**
 * BalanceChip — a day job's running balance against its contract, small
 * enough for a list row: "+4.5 h", "−2.0 h" or "even", coloured by which
 * way it leans, with the long form as the tooltip. A visually hidden
 * prefix says what the number is: inside a row's button the bare "+4.5 h"
 * would be read with nothing calling it a balance, and a title is not
 * announced.
 */

import { cn } from "@/shared/lib";
import { type BalanceTone, balanceTone, describeBalance, formatSignedHours } from "../model";

const TONE_CLASS: Record<BalanceTone, string> = {
	over: "bg-success/15 text-success-ink",
	owed: "bg-destructive/15 text-destructive-ink",
	even: "bg-secondary text-muted-foreground",
};

interface BalanceChipProps {
	hours: number;
	className?: string;
}

export function BalanceChip({ hours, className }: BalanceChipProps) {
	return (
		<span
			className={cn(
				"inline-flex items-center rounded-full px-1.5 py-px text-[10px] font-bold tabular-nums whitespace-nowrap shrink-0",
				TONE_CLASS[balanceTone(hours)],
				className,
			)}
			title={`Balance against the contract: ${describeBalance(hours)}`}
		>
			<span className="sr-only">Balance against the contract: </span>
			{formatSignedHours(hours)}
		</span>
	);
}
