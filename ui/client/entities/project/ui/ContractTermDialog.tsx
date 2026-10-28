/**
 * ContractTermDialog — one term, added or edited, in a dialog. Shared by the
 * two places a term is written: the member's Contract panel on the project
 * page, and the employer's managed-contract dialog on the organisation page.
 * One dialog so a term is validated, described and corrected the same way
 * whoever holds the pen.
 *
 * The host owns the save: `onSave` hands over the term and a callback that
 * brings a failed write's 422 back to the inputs, since only the host knows
 * which request carried it. `fieldPrefix` is where the contract sits in that
 * request's body — "" on the member's `PUT /contract`, "contract" on the
 * organisation's, which wraps it beside `managed`.
 */

import { useState } from "react";
import { apiFieldErrors, describeError } from "@/shared/api";
import { Button, Dialog } from "@/shared/ui";
import type { ContractTerm, TermFieldErrors, TermFormValues } from "../model";
import { contractFieldErrors, termFromForm, validateTerm } from "../model";
import { ContractTermFields } from "./ContractTermFields";

export interface ContractTermDialogProps {
	title: string;
	initial: TermFormValues;
	/** effective_from dates of the other terms — no two may start on one day. */
	takenDates: string[];
	submitting: boolean;
	onClose: () => void;
	/** Hands the term over; `onError` brings a failed save's 422 back to the inputs. */
	onSave: (term: ContractTerm, onError: (err: unknown, savedIndex: number) => void) => void;
	/** Where the contract sits in the request body: "" when it is the body. */
	fieldPrefix?: string;
	/** Where focus goes on close when the control that opened the dialog has gone. */
	returnFocus?: () => HTMLElement | null | undefined;
}

export function ContractTermDialog({
	title,
	initial,
	takenDates,
	submitting,
	onClose,
	onSave,
	fieldPrefix = "",
	returnFocus,
}: ContractTermDialogProps) {
	const [values, setValues] = useState<TermFormValues>(initial);
	const [errors, setErrors] = useState<TermFieldErrors>({});
	const [general, setGeneral] = useState<string[]>([]);

	const handleSubmit = () => {
		const next = validateTerm(values);
		if (!next.effectiveFrom && takenDates.includes(values.effectiveFrom)) {
			next.effectiveFrom = "Another term already starts on this day";
		}
		setErrors(next);
		setGeneral([]);
		if (Object.keys(next).length > 0) return;
		onSave(termFromForm(values), (err, savedIndex) => {
			const sorted = contractFieldErrors(apiFieldErrors(err), fieldPrefix, savedIndex);
			setErrors(sorted.term);
			const messages = [...sorted.general];
			if (messages.length === 0 && Object.keys(sorted.term).length === 0) {
				messages.push(describeError(err, "Failed to save contract"));
			}
			setGeneral(messages);
		});
	};

	return (
		<Dialog
			open
			onClose={onClose}
			returnFocus={returnFocus}
			title={title}
			description="Any weekday works: a change on a Wednesday charges Monday and Tuesday at the old rate."
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					handleSubmit();
				}}
				className="space-y-4"
				noValidate
			>
				<ContractTermFields
					values={values}
					onChange={setValues}
					errors={errors}
					dateLabel="From"
					withNote
					autoFocusField="effectiveFrom"
				/>
				{general.length > 0 && (
					<div className="text-sm text-destructive-ink space-y-0.5" role="alert">
						{general.map((message) => (
							<p key={message}>{message}</p>
						))}
					</div>
				)}
				<div className="flex gap-2 pt-1">
					<Button type="submit" disabled={submitting} className="flex-1">
						{submitting ? "Saving…" : "Save term"}
					</Button>
					<Button type="button" variant="outline" onClick={onClose}>
						Cancel
					</Button>
				</div>
			</form>
		</Dialog>
	);
}
