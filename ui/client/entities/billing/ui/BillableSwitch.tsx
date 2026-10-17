/**
 * BillableSwitch — one entry's Billable pill, where the entry is seen: a
 * session row on the project page, a row of the Clients page's entries. It
 * shows what the report counts (`entryBillable`, or the API's own entry),
 * and a tap marks the entry the other way, whatever its project's term
 * says. A marked entry carries a quiet "marked by you" and a way back to
 * the project's rule. The mark changes in the cache at once and is put back
 * if the write fails, with the API's reason in a toast.
 */

import { RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { describeError } from "@/shared/api";
import { cn } from "@/shared/lib";
import { useClearEntryBillable, useSetEntryBillable } from "../api";

export interface BillableSwitchProps {
	beatId: string;
	billable: boolean;
	/** A mark of the user's decides it, not the project's term. */
	overridden: boolean;
	/** What the entry is, for the controls' names: "Thu Oct 2, 09:00". */
	entryLabel: string;
}

const PILL =
	"inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-bold whitespace-nowrap transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

export function BillableSwitch({ beatId, billable, overridden, entryLabel }: BillableSwitchProps) {
	const setMark = useSetEntryBillable();
	const clearMark = useClearEntryBillable();
	const busy = setMark.isPending || clearMark.isPending;

	const toggle = () =>
		setMark.mutate(
			{ beatId, billable: !billable },
			{ onError: (err) => toast.error(describeError(err, "Could not mark the entry")) },
		);
	const reset = () =>
		clearMark.mutate(
			{ beatId },
			{ onError: (err) => toast.error(describeError(err, "Could not reset the entry")) },
		);

	return (
		<span className="inline-flex items-center gap-1.5 shrink-0">
			<button
				type="button"
				role="switch"
				aria-checked={billable}
				aria-label={`Billable: ${entryLabel}`}
				onClick={toggle}
				disabled={busy}
				className={cn(
					PILL,
					billable
						? "bg-tint-holiday text-tint-holiday-ink"
						: "bg-secondary text-muted-foreground hover:text-foreground",
				)}
			>
				{billable ? "Billable" : "Not billable"}
			</button>
			{overridden && (
				<>
					<span className="text-[10.5px] font-medium text-muted-foreground whitespace-nowrap">
						marked by you
					</span>
					<button
						type="button"
						onClick={reset}
						disabled={busy}
						aria-label={`Use the project's rule: ${entryLabel}`}
						title="Use the project's rule"
						className="grid place-items-center w-5 h-5 rounded-full text-muted-foreground hover:bg-sidebar-accent hover:text-foreground transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
					>
						<RotateCcw className="w-3 h-3" aria-hidden="true" />
					</button>
				</>
			)}
		</span>
	);
}
