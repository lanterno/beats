/**
 * RequestAbsenceDialog — asking for a day off on a managed assignment
 * (docs/organisations.md, stage 3). The contract is the organisation's to
 * write, so the member does not book: they ask, and a decider approves the
 * request into a real absence. One day, the same type wording as the booking
 * dialog, a half-day, and a note only the manager reads — the organisation's
 * record never shows it, and the dialog says so.
 */

import { useId, useState } from "react";
import { toast } from "sonner";
import { ABSENCE_TYPE_LABELS, type AbsenceType } from "@/entities/absence";
import { useRequestAbsence } from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { cn } from "@/shared/lib";
import { Button, Dialog } from "@/shared/ui";
import { LABEL } from "./styles";

export interface RequestAbsenceDialogProps {
	organisationId: string;
	projectId: string;
	/** The day the request opens on. */
	defaultDate: string;
	onClose: () => void;
	/** Where focus goes on close when the control that opened the dialog has gone. */
	returnFocus?: () => HTMLElement | null | undefined;
}

const TYPES: AbsenceType[] = ["vacation", "sick", "other"];

const FIELD =
	"w-full bg-secondary border-0 rounded-xl text-foreground px-3 py-2 text-[13.5px] font-mono font-bold focus:outline-hidden focus:ring-[3px] focus:ring-accent";

export function RequestAbsenceDialog({
	organisationId,
	projectId,
	defaultDate,
	onClose,
	returnFocus,
}: RequestAbsenceDialogProps) {
	const id = useId();
	const [date, setDate] = useState(defaultDate);
	const [type, setType] = useState<AbsenceType>("vacation");
	const [halfDay, setHalfDay] = useState(false);
	const [note, setNote] = useState("");
	const [error, setError] = useState<string | null>(null);
	const request = useRequestAbsence(organisationId);

	const submit = () => {
		if (!date) {
			setError("Enter a day.");
			return;
		}
		setError(null);
		request.mutate(
			{ projectId, date, type, halfDay, note: note.trim() || undefined },
			{
				onSuccess: () => {
					toast.success("Time off requested");
					onClose();
				},
				// A 409 (CONTRACT_MANAGED, PERIOD_APPROVED, …) in the API's words.
				onError: (err) => setError(describeError(err, "Failed to request time off")),
			},
		);
	};

	return (
		<Dialog
			open
			onClose={onClose}
			returnFocus={returnFocus}
			title="Ask for time off"
			description="The contract is managed: a decider approves the request into a booked day."
			contentClassName="sm:w-full sm:max-w-[420px]"
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					submit();
				}}
				noValidate
			>
				<fieldset className="min-w-0 border-0 p-0 m-0">
					<legend className={cn(LABEL, "mb-[5px]")}>Type</legend>
					<div className="inline-flex gap-1 p-1 rounded-full bg-secondary">
						{TYPES.map((t) => (
							<button
								key={t}
								type="button"
								aria-pressed={type === t}
								onClick={() => setType(t)}
								className={cn(
									"px-[13px] py-[5px] rounded-full text-[12.5px] font-bold transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
									type === t ? "bg-accent text-accent-foreground" : "text-muted-foreground",
								)}
							>
								{ABSENCE_TYPE_LABELS[t]}
							</button>
						))}
					</div>
				</fieldset>

				<div className="mt-3">
					<label htmlFor={`${id}-date`} className={cn(LABEL, "block mb-[5px]")}>
						Day
					</label>
					<input
						id={`${id}-date`}
						type="date"
						value={date}
						onChange={(e) => setDate(e.target.value)}
						className={FIELD}
					/>
				</div>

				<label className="flex items-center gap-2 text-[13px] text-foreground mt-3.5 font-medium">
					<input
						type="checkbox"
						checked={halfDay}
						onChange={(e) => setHalfDay(e.target.checked)}
						className="accent-[hsl(var(--accent))]"
					/>
					Half day
				</label>

				<div className="mt-3">
					<label htmlFor={`${id}-note`} className={cn(LABEL, "block mb-[5px]")}>
						Note
					</label>
					<input
						id={`${id}-note`}
						type="text"
						value={note}
						onChange={(e) => setNote(e.target.value)}
						placeholder="optional"
						className={cn(FIELD, "font-body font-medium")}
					/>
					<p className="mt-1.5 text-xs text-muted-foreground font-medium leading-normal">
						Your manager reads this note; the organisation's record never shows it.
					</p>
				</div>

				{error && (
					<p role="alert" className="mt-2.5 text-[12.5px] text-destructive-ink">
						{error}
					</p>
				)}

				<div className="flex justify-end gap-2.5 mt-[18px]">
					<Button
						type="button"
						variant="secondary"
						size="sm"
						onClick={onClose}
						disabled={request.isPending}
					>
						Cancel
					</Button>
					<Button type="submit" size="sm" disabled={request.isPending}>
						{request.isPending ? "Asking…" : "Ask"}
					</Button>
				</div>
			</form>
		</Dialog>
	);
}
