/**
 * EnterTimeDialog — a decider enters worked time for a member: a date, a
 * start, an end and a note. It lands on the member's own timeline, marked
 * as entered by the decider, and in the audit log — which the dialog says.
 * Times are read in the decider's own timezone, and the dialog says which,
 * since the member may live in another; an end at or before the start
 * means the shift ran past midnight and is entered as the next day.
 */

import { useId, useState } from "react";
import { toast } from "sonner";
import { useEnterTime } from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { Button, Dialog } from "@/shared/ui";
import { ERROR, FIELD, LABEL, LEAD } from "./styles";

export function EnterTimeDialog({
	organisationId,
	projectId,
	projectName,
	userId,
	memberName,
	onClose,
}: {
	organisationId: string;
	projectId: string;
	projectName: string;
	userId: string;
	memberName: string;
	onClose: () => void;
}) {
	const id = useId();
	const enter = useEnterTime(organisationId);
	// Today, in the decider's zone — the one the times are read in.
	const [date, setDate] = useState(() => new Date().toLocaleDateString("en-CA"));
	const [start, setStart] = useState("");
	const [end, setEnd] = useState("");
	const [note, setNote] = useState("");
	const [error, setError] = useState("");
	const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
	const overnight = Boolean(start && end && end <= start);

	const submit = () => {
		if (!date || !start || !end) {
			setError("A date, a start and an end are needed.");
			return;
		}
		const startAt = new Date(`${date}T${start}`);
		const endAt = new Date(`${date}T${end}`);
		// A night shift: 22:00 to 02:00 ends the next day, and the form says
		// so before it is sent rather than refusing the shape night work has.
		if (endAt <= startAt) endAt.setDate(endAt.getDate() + 1);
		if (Number.isNaN(startAt.getTime()) || Number.isNaN(endAt.getTime())) {
			setError("The date or a time could not be read.");
			return;
		}
		setError("");
		enter.mutate(
			{
				projectId,
				userId,
				input: {
					start: startAt.toISOString(),
					end: endAt.toISOString(),
					note: note.trim() || undefined,
				},
			},
			{
				onSuccess: () => {
					toast.success(`Time entered for ${memberName}`);
					onClose();
				},
				onError: (err) => setError(describeError(err, "The time could not be entered.")),
			},
		);
	};

	return (
		<Dialog
			open
			onClose={() => !enter.isPending && onClose()}
			title={`Enter time for ${memberName}`}
			description={`On ${projectName}.`}
			contentClassName="sm:w-full sm:max-w-[420px]"
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					submit();
				}}
				noValidate
				className="space-y-3"
			>
				<div>
					<label htmlFor={`${id}-date`} className={LABEL}>
						Date
					</label>
					<input
						id={`${id}-date`}
						type="date"
						value={date}
						onChange={(e) => setDate(e.target.value)}
						autoFocus
						className={FIELD}
					/>
				</div>
				<div className="grid grid-cols-2 gap-3">
					<div>
						<label htmlFor={`${id}-start`} className={LABEL}>
							Start
						</label>
						<input
							id={`${id}-start`}
							type="time"
							value={start}
							onChange={(e) => setStart(e.target.value)}
							className={FIELD}
						/>
					</div>
					<div>
						<label htmlFor={`${id}-end`} className={LABEL}>
							End{overnight && " — the next day"}
						</label>
						<input
							id={`${id}-end`}
							type="time"
							value={end}
							onChange={(e) => setEnd(e.target.value)}
							className={FIELD}
						/>
					</div>
				</div>
				<div>
					<label htmlFor={`${id}-note`} className={LABEL}>
						Note (optional)
					</label>
					<input
						id={`${id}-note`}
						type="text"
						value={note}
						onChange={(e) => setNote(e.target.value)}
						maxLength={500}
						className={FIELD}
					/>
				</div>
				<p className={LEAD}>
					Times are in your timezone ({timezone}). Lands on {memberName}'s own timeline, marked as
					entered by you, and in the audit log.
				</p>
				{error && (
					<p role="alert" className={ERROR}>
						{error}
					</p>
				)}
				<div className="flex justify-end gap-2.5 pt-1">
					<Button
						type="button"
						variant="secondary"
						size="sm"
						onClick={onClose}
						disabled={enter.isPending}
					>
						Cancel
					</Button>
					<Button type="submit" size="sm" disabled={enter.isPending}>
						{enter.isPending ? "Entering…" : "Enter time"}
					</Button>
				</div>
			</form>
		</Dialog>
	);
}
