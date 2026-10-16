/**
 * AdjustmentDialog — a payout, a credit, a reset or a cap on a day job's
 * balance, dated, instead of an edit to the opening balance (docs/project-page.md).
 * Pay out and Credit are one kind on the wire, a signed `delta`; Reset to
 * and Cap at send their target. Each takes effect at the start of its day,
 * which may run from the contract's first day through today.
 *
 * One adjustment per day: saving onto a day that already holds one replaces
 * it, and the dialog says so when the ledger shows that day's. Changing an
 * adjustment's date posts on the new day before deleting the old, so a
 * failure leaves the old one in place. No new balance is previewed here —
 * what a reset or a cap moves is the API's to work out (Decision 11); the
 * ledger's row says it once saved. A refusal is the API's message, inline.
 */

import { useId, useState } from "react";
import { toast } from "sonner";
import type { AdjustmentKind, LedgerAdjustment } from "@/entities/project";
import { useRecordAdjustment, useRemoveAdjustment } from "@/entities/project";
import { describeError } from "@/shared/api";
import { cn, parseIsoDate } from "@/shared/lib";
import { Button, Dialog } from "@/shared/ui";
import { longDate } from "./dates";
import { LABEL } from "./styles";

export interface AdjustmentDialogProps {
	projectId: string;
	/** The contract's first day: the earliest an adjustment may be dated. */
	since: string;
	todayIso: string;
	/** Every adjustment the ledger holds, to warn before one is replaced. */
	adjustments: LedgerAdjustment[];
	/** The adjustment to change or remove; a new one when left out. */
	editing?: LedgerAdjustment;
	onClose: () => void;
	/** Where focus goes on close when the row that opened the dialog has gone. */
	returnFocus?: () => HTMLElement | null | undefined;
}

type Mode = "payout" | "credit" | "reset" | "cap";

const MODES: { mode: Mode; label: string; hint: string }[] = [
	{ mode: "payout", label: "Pay out", hint: "Takes the hours off the balance as the day starts." },
	{ mode: "credit", label: "Credit", hint: "Adds the hours to the balance as the day starts." },
	{
		mode: "reset",
		label: "Reset to",
		hint: "The balance becomes this figure as the day starts; the day's work counts from it.",
	},
	{
		mode: "cap",
		label: "Cap at",
		hint: "A balance above this is brought down to it as the day starts; one below is left alone.",
	},
];

/** The API's bound on an adjustment's hours. */
const MAX_HOURS = 10_000;

const FIELD =
	"w-full bg-secondary border-0 rounded-xl text-foreground px-3 py-2 text-[13.5px] font-mono font-bold focus:outline-hidden focus:ring-[3px] focus:ring-accent";

function modeOf(adjustment: LedgerAdjustment): Mode {
	if (adjustment.kind === "delta") return adjustment.hours < 0 ? "payout" : "credit";
	return adjustment.kind;
}

const KIND_OF: Record<Mode, AdjustmentKind> = {
	payout: "delta",
	credit: "delta",
	reset: "reset",
	cap: "cap",
};

/** "the payout", "the reset" — an adjustment as the replace warning names it. */
function described(adjustment: LedgerAdjustment): string {
	switch (modeOf(adjustment)) {
		case "payout":
			return "the payout";
		case "credit":
			return "the credit";
		case "reset":
			return "the reset";
		case "cap":
			return "the cap";
	}
}

/** The hours as the field shows them: a delta's magnitude, a target as it is. */
function fieldHours(adjustment: LedgerAdjustment): string {
	const hours = adjustment.kind === "delta" ? Math.abs(adjustment.hours) : adjustment.hours;
	return String(Math.round(hours * 100) / 100);
}

/** The signed hours to send, or the reason there are none. */
function parseHours(mode: Mode, text: string): { hours: number } | { error: string } {
	if (text.trim() === "") return { error: "Enter the hours." };
	const value = Number(text);
	if (!Number.isFinite(value)) return { error: "Enter the hours as a number." };
	if (Math.abs(value) > MAX_HOURS)
		return { error: `At most ${MAX_HOURS.toLocaleString("en-US")} h.` };
	if (mode === "payout" || mode === "credit") {
		if (value <= 0) return { error: "Enter the hours to move, more than 0." };
		return { hours: mode === "payout" ? -value : value };
	}
	if (mode === "cap" && value < 0) return { error: "A cap is 0 h or more." };
	return { hours: value };
}

export function AdjustmentDialog({
	projectId,
	since,
	todayIso,
	adjustments,
	editing,
	onClose,
	returnFocus,
}: AdjustmentDialogProps) {
	const id = useId();
	const [mode, setMode] = useState<Mode>(editing ? modeOf(editing) : "payout");
	const [hours, setHours] = useState(editing ? fieldHours(editing) : "");
	const [date, setDate] = useState(editing?.date ?? todayIso);
	const [note, setNote] = useState(editing?.note ?? "");
	const [touched, setTouched] = useState(false);
	const [busy, setBusy] = useState(false);
	const [refusal, setRefusal] = useState<string | null>(null);

	const record = useRecordAdjustment();
	const remove = useRemoveAdjustment();

	const parsed = parseHours(mode, hours);
	const hoursError = touched && "error" in parsed ? parsed.error : null;
	const dateError = !parseIsoDate(date)
		? "Enter the day."
		: date < since
			? `The contract starts ${longDate(since)}.`
			: date > todayIso
				? "An adjustment can be dated today at the latest."
				: null;
	const taken = adjustments.find((a) => a.date === date && a.id !== editing?.id);
	const hint = MODES.find((m) => m.mode === mode)?.hint;

	const save = async () => {
		setTouched(true);
		if ("error" in parsed || dateError) return;
		setBusy(true);
		setRefusal(null);
		try {
			await record.mutateAsync({
				projectId,
				input: { date, kind: KIND_OF[mode], hours: parsed.hours, note },
			});
			// Moved to another day: the new one is on record, so the old can go.
			if (editing && editing.date !== date) {
				await remove.mutateAsync({ projectId, adjustmentId: editing.id });
			}
			toast.success(editing ? "Adjustment saved" : "Balance adjusted");
			onClose();
		} catch (error) {
			setRefusal(describeError(error, "Failed to save the adjustment"));
		} finally {
			setBusy(false);
		}
	};

	const removeIt = async () => {
		if (!editing) return;
		setBusy(true);
		setRefusal(null);
		try {
			await remove.mutateAsync({ projectId, adjustmentId: editing.id });
			toast.success("Adjustment removed");
			onClose();
		} catch (error) {
			setRefusal(describeError(error, "Failed to remove the adjustment"));
		} finally {
			setBusy(false);
		}
	};

	const close = () => {
		if (!busy) onClose();
	};

	return (
		<Dialog
			open
			onClose={close}
			returnFocus={returnFocus}
			title={editing ? "Change adjustment" : "Adjust balance"}
			description="A payout, a credit, a reset or a cap, from the start of its day."
			contentClassName="sm:w-full sm:max-w-[420px]"
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					void save();
				}}
				noValidate
			>
				<fieldset className="min-w-0 border-0 p-0 m-0">
					<legend className={cn(LABEL, "mb-[5px]")}>Adjustment</legend>
					<div className="inline-flex flex-wrap gap-1 p-1 rounded-full bg-secondary">
						{MODES.map((m) => (
							<button
								key={m.mode}
								type="button"
								aria-pressed={mode === m.mode}
								onClick={() => setMode(m.mode)}
								className={cn(
									"px-[13px] py-[5px] rounded-full text-[12.5px] font-bold transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
									mode === m.mode ? "bg-accent text-accent-foreground" : "text-muted-foreground",
								)}
							>
								{m.label}
							</button>
						))}
					</div>
				</fieldset>
				{hint && <p className="mt-1.5 text-xs font-medium text-muted-foreground">{hint}</p>}

				<div className="mt-3 grid grid-cols-2 gap-3">
					<div>
						<label htmlFor={`${id}-hours`} className={cn(LABEL, "block mb-[5px]")}>
							Hours
						</label>
						<input
							id={`${id}-hours`}
							type="number"
							inputMode="decimal"
							step="0.25"
							min={mode === "reset" ? -MAX_HOURS : 0}
							max={MAX_HOURS}
							value={hours}
							onChange={(e) => setHours(e.target.value)}
							onBlur={() => setTouched(true)}
							aria-invalid={hoursError ? true : undefined}
							aria-describedby={hoursError ? `${id}-hours-error` : undefined}
							className={FIELD}
						/>
					</div>
					<div>
						<label htmlFor={`${id}-date`} className={cn(LABEL, "block mb-[5px]")}>
							Day
						</label>
						<input
							id={`${id}-date`}
							type="date"
							value={date}
							min={since}
							max={todayIso}
							onChange={(e) => setDate(e.target.value)}
							aria-invalid={dateError ? true : undefined}
							aria-describedby={dateError ? `${id}-date-error` : undefined}
							className={FIELD}
						/>
					</div>
				</div>
				{hoursError && (
					<p id={`${id}-hours-error`} className="mt-1.5 text-xs text-destructive-ink">
						{hoursError}
					</p>
				)}
				{dateError && (
					<p id={`${id}-date-error`} className="mt-1.5 text-xs text-destructive-ink">
						{dateError}
					</p>
				)}
				{taken && !dateError && (
					<p className="mt-1.5 text-xs font-medium text-muted-foreground" aria-live="polite">
						Replaces {described(taken)} on this day.
					</p>
				)}

				<div className="mt-3">
					<label htmlFor={`${id}-note`} className={cn(LABEL, "block mb-[5px]")}>
						Note
					</label>
					<input
						id={`${id}-note`}
						type="text"
						value={note}
						onChange={(e) => setNote(e.target.value)}
						placeholder="e.g. Paid out with the August salary"
						className={cn(FIELD, "font-body font-medium")}
					/>
				</div>

				{refusal && (
					<p className="mt-2.5 text-[12.5px] text-destructive-ink" role="alert">
						{refusal}
					</p>
				)}

				<div className="flex flex-wrap items-center gap-2.5 mt-[18px]">
					{editing && (
						<Button
							type="button"
							variant="ghost"
							size="sm"
							className="text-destructive hover:text-destructive"
							disabled={busy}
							onClick={() => void removeIt()}
						>
							Remove
						</Button>
					)}
					<div className="ml-auto flex gap-2.5">
						<Button type="button" variant="secondary" size="sm" onClick={close} disabled={busy}>
							Cancel
						</Button>
						<Button type="submit" size="sm" disabled={busy}>
							{busy ? "Saving…" : "Save"}
						</Button>
					</div>
				</div>
			</form>
		</Dialog>
	);
}
