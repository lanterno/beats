/**
 * CommentDialog — one dialog for every decision that may carry a comment:
 * approve or decline a day off, approve a month, ask for changes, reopen.
 * It replaces two near-identical dialogs (the timesheets' ActionDialog and
 * the absences' DecisionDialog), and it always says whose and what is being
 * decided — the one dialog that didn't, Reopen, was the destructive one.
 * A failure shows inside the dialog, which stays open; a toast beside an
 * open dialog was easy to miss.
 */

import { type ReactNode, useId, useState } from "react";
import { describeError } from "@/shared/api";
import { Button, Dialog } from "@/shared/ui";
import { ERROR, FIELD, LABEL } from "./styles";

export interface CommentDialogProps {
	title: string;
	/** Whose and what: "Nadia · Backend · September 2026". Always said. */
	context: string;
	/** Anything the decider should read first — figures, a link to them. */
	hint?: ReactNode;
	/** The comment field's label, e.g. "What should change". */
	commentLabel: string;
	/** A decision that means nothing without words requires them. */
	commentRequired?: boolean;
	confirmLabel: string;
	/** While sending: "Sending…". */
	busyLabel: string;
	/** Declining and reopening are not the page's primary action. */
	danger?: boolean;
	onClose: () => void;
	/** Rejects to keep the dialog open with the error inside it. */
	onSend: (comment: string) => Promise<void>;
}

export function CommentDialog({
	title,
	context,
	hint,
	commentLabel,
	commentRequired = false,
	confirmLabel,
	busyLabel,
	danger = false,
	onClose,
	onSend,
}: CommentDialogProps) {
	const id = useId();
	const [comment, setComment] = useState("");
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState("");

	const send = async () => {
		const text = comment.trim();
		if (commentRequired && !text) {
			setError(`${commentLabel} can't be empty.`);
			return;
		}
		setError("");
		setBusy(true);
		try {
			await onSend(text);
		} catch (err) {
			setError(describeError(err, "The decision could not be sent."));
			setBusy(false);
		}
	};

	return (
		<Dialog
			open
			onClose={() => !busy && onClose()}
			title={title}
			description={context}
			contentClassName="sm:w-full sm:max-w-[400px]"
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					void send();
				}}
				noValidate
				className="space-y-3"
			>
				{hint}
				<div>
					<label htmlFor={`${id}-comment`} className={LABEL}>
						{commentLabel}
					</label>
					<input
						id={`${id}-comment`}
						type="text"
						value={comment}
						onChange={(e) => setComment(e.target.value)}
						maxLength={500}
						autoFocus
						aria-invalid={error ? true : undefined}
						aria-describedby={error ? `${id}-error` : undefined}
						className={FIELD}
					/>
				</div>
				{error && (
					<p id={`${id}-error`} role="alert" className={ERROR}>
						{error}
					</p>
				)}
				<div className="flex justify-end gap-2.5 pt-1">
					<Button type="button" variant="secondary" size="sm" onClick={onClose} disabled={busy}>
						Cancel
					</Button>
					<Button
						type="submit"
						size="sm"
						variant={danger ? "destructive" : "default"}
						disabled={busy}
					>
						{busy ? busyLabel : confirmLabel}
					</Button>
				</div>
			</form>
		</Dialog>
	);
}
