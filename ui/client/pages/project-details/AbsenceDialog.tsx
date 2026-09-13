/**
 * AbsenceDialog — booking time off on a day job (the mockup's renderDialog):
 * the type, From and Through, the month grid as their picker, half day, a
 * note, and a line saying what the booking does to the week. Saving records
 * one absence per weekday in the range — weekends and the region's public
 * holidays are skipped, since the contract owes nothing on them — as one run
 * of writes with one toast at the end. A range whose every weekday is already
 * booked can be removed, and so can an absence stored on a holiday.
 *
 * A booked day keeps its own note unless one is typed: the field starts from
 * the note the days share, or empty when they differ, and an untouched field
 * is not a request to clear them. While a run is saving the dialog stays
 * open — closed under it, the writes went on regardless.
 *
 * The absence hooks invalidate the absences, the contract weeks and the
 * ledger once the run is over, so the standing, the days and the rail follow.
 */

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import type { Absence, AbsenceType } from "@/entities/absence";
import {
	ABSENCE_TYPE_LABELS,
	useAbsences,
	useRecordAbsences,
	useRemoveAbsences,
} from "@/entities/absence";
import type { Contract, Project } from "@/entities/project";
import {
	termHoursPerDay,
	termOn,
	useContractWeek,
	useProjectHolidays,
	weekLabel,
} from "@/entities/project";
import { describeError } from "@/shared/api";
import { addIsoDays, cn, mondayOfIso, parseIsoDate } from "@/shared/lib";
import { Button, Dialog } from "@/shared/ui";
import { isWeekdayIso, longDate } from "./dates";
import { LABEL, TINT } from "./styles";

export interface AbsenceDialogProps {
	project: Pick<Project, "id" | "contract">;
	todayIso: string;
	/** The first day to book. */
	from: string;
	/** The last day; defaults to `from`. */
	through?: string;
	/** What the days already hold, to start the fields from. */
	initial?: { type: AbsenceType; halfDay: boolean; note?: string };
	onClose: () => void;
	/** Where focus goes on close when the control that opened the dialog has gone. */
	returnFocus?: () => HTMLElement | null | undefined;
}

/** What the dialog opens on: the days, and what they already hold. */
export type AbsenceBooking = Pick<AbsenceDialogProps, "from" | "through" | "initial">;

const TYPES: AbsenceType[] = ["vacation", "sick", "other"];
const WEEKDAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
/** A booking longer than this is a typo in the year, not a sabbatical to fan out. */
const MAX_DAYS = 366;
const COUNT_WORDS = [
	"No",
	"One",
	"Two",
	"Three",
	"Four",
	"Five",
	"Six",
	"Seven",
	"Eight",
	"Nine",
	"Ten",
];

const FIELD =
	"w-full bg-secondary border-0 rounded-xl text-foreground px-3 py-2 text-[13.5px] font-mono font-bold focus:outline-hidden focus:ring-[3px] focus:ring-accent";

function monthOf(iso: string): string {
	return `${iso.slice(0, 7)}-01`;
}

function addMonths(firstOfMonth: string, n: number): string {
	const d = parseIsoDate(firstOfMonth) ?? new Date();
	const moved = new Date(d.getFullYear(), d.getMonth() + n, 1, 12);
	return `${moved.getFullYear()}-${String(moved.getMonth() + 1).padStart(2, "0")}-01`;
}

function daysInMonth(firstOfMonth: string): number {
	const d = parseIsoDate(firstOfMonth) ?? new Date();
	return new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
}

/** Every day from `from` through `through`; null when either is not a date or they are reversed. */
function daysOf(from: string, through: string): string[] | null {
	if (!parseIsoDate(from) || !parseIsoDate(through) || through < from) return null;
	const out: string[] = [];
	for (let d = from; d <= through && out.length <= MAX_DAYS; d = addIsoDays(d, 1)) out.push(d);
	return out;
}

/** What one weekday owes under the contract: its term's day, nothing before it or after the end. */
function hoursDue(contract: Contract, iso: string): number {
	if (contract.endedOn && iso > contract.endedOn) return 0;
	const term = termOn(contract, iso);
	return term ? (termHoursPerDay(term) ?? 0) : 0;
}

/**
 * "This week's expectation drops by 6.7 h, to 26.9 h. One weekday; weekends
 * and public holidays are skipped." — the booking's cost against what is
 * already booked on those days, named against the week when the range sits
 * in one.
 */
function costLine(input: {
	contract: Contract | undefined;
	bookable: string[];
	halfDay: boolean;
	existing: Map<string, Absence>;
	/** The range's week against the contract, when the range sits in one week. */
	week?: { weekOf: string; expected?: number };
	todayIso: string;
}): string {
	const { contract, bookable, halfDay, existing, week, todayIso } = input;
	if (!contract) return "Counts once a contract is set.";
	if (bookable.length === 0) return "Nothing to book: weekends and public holidays are skipped.";
	let delta = 0;
	let due = false;
	for (const iso of bookable) {
		const perDay = hoursDue(contract, iso);
		if (perDay > 0) due = true;
		const was = existing.get(iso);
		const before = was ? (was.halfDay ? 0.5 : 1) : 0;
		delta += perDay * ((halfDay ? 0.5 : 1) - before);
	}
	if (!due) {
		return `Nothing is due under this term; the ${bookable.length === 1 ? "day is" : "days are"} recorded.`;
	}
	const expected = week?.expected;
	const whose =
		week && expected !== undefined
			? `${weekLabel(week.weekOf, todayIso)}'s expectation`
			: "The expectation";
	const amount = Math.abs(delta).toFixed(1);
	const to = expected !== undefined ? `, to ${(expected - delta).toFixed(1)} h` : "";
	const head =
		amount === "0.0"
			? `${whose} stays as it is.`
			: `${whose} ${delta > 0 ? "drops" : "rises"} by ${amount} h${to}.`;
	const n = bookable.length;
	return `${head} ${COUNT_WORDS[n] ?? n} weekday${n === 1 ? "" : "s"}; weekends and public holidays are skipped.`;
}

export function AbsenceDialog({
	project,
	todayIso,
	from: initialFrom,
	through: initialThrough,
	initial,
	onClose,
	returnFocus,
}: AbsenceDialogProps) {
	const id = useId();
	const [type, setType] = useState<AbsenceType>(initial?.type ?? "vacation");
	const [halfDay, setHalfDay] = useState(initial?.halfDay ?? false);
	const [note, setNote] = useState(initial?.note ?? "");
	const [noteEdited, setNoteEdited] = useState(false);
	const [from, setFrom] = useState(initialFrom);
	const [through, setThrough] = useState(initialThrough ?? initialFrom);
	const [month, setMonth] = useState(monthOf(initialFrom));
	const [picking, setPicking] = useState<"from" | "through">("from");
	const [busy, setBusy] = useState(false);

	const record = useRecordAbsences();
	const remove = useRemoveAbsences();
	const contract = project.contract;

	const range = daysOf(from, through);
	const tooLong = range !== null && range.length > MAX_DAYS;
	const valid = range !== null && !tooLong;
	const monthEnd = `${month.slice(0, 8)}${String(daysInMonth(month)).padStart(2, "0")}`;

	const { data: monthAbsences } = useAbsences(project.id, { start: month, end: monthEnd });
	const { data: rangeAbsences, isLoading: rangeLoading } = useAbsences(
		project.id,
		valid ? { start: from, end: through } : { start: month, end: month },
	);
	const monthYear = Number(month.slice(0, 4));
	const fromYear = parseIsoDate(from)?.getFullYear() ?? monthYear;
	const throughYear = parseIsoDate(through)?.getFullYear() ?? fromYear;
	const monthHolidays = useProjectHolidays(project.id, monthYear);
	const fromHolidays = useProjectHolidays(project.id, fromYear);
	const throughHolidays = useProjectHolidays(project.id, throughYear);
	const holidays = new Map(
		[
			...(monthHolidays.data ?? []),
			...(fromHolidays.data ?? []),
			...(throughHolidays.data ?? []),
		].map((h) => [h.date, h.name]),
	);
	const holidaysLoading = fromHolidays.isLoading || throughHolidays.isLoading;

	const weekOf = valid ? mondayOfIso(from) : mondayOfIso(todayIso);
	const oneWeek = valid && mondayOfIso(through) === weekOf;
	const { data: week } = useContractWeek(project.id, weekOf, { enabled: !!contract && oneWeek });

	const bookable = valid ? range.filter((d) => isWeekdayIso(d) && !holidays.has(d)) : [];
	const onRecord = new Map(
		(valid ? (rangeAbsences ?? []) : [])
			.filter((a) => a.date >= from && a.date <= through)
			.map((a) => [a.date, a]),
	);
	// Every bookable weekday in the range on record — vacuously so on a range of
	// holidays alone, so an absence stored on one before the region was set can
	// still be taken back.
	const removable = onRecord.size > 0 && bookable.every((d) => onRecord.has(d));
	const mixedNotes =
		!noteEdited && new Set([...onRecord.values()].map((a) => a.note ?? "")).size > 1;
	const byDate = new Map((monthAbsences ?? []).map((a) => [a.date, a]));

	const cost = valid
		? costLine({
				contract,
				bookable,
				halfDay,
				existing: onRecord,
				week: oneWeek && week ? { weekOf, expected: week.expected } : undefined,
				todayIso,
			})
		: null;

	const changeFrom = (value: string) => {
		setFrom(value);
		if (!parseIsoDate(value)) return;
		if (!parseIsoDate(through) || through < value || through === from) setThrough(value);
		setMonth(monthOf(value));
	};

	const changeThrough = (value: string) => {
		setThrough(value);
		if (parseIsoDate(value)) setMonth(monthOf(value));
	};

	// The grid sets From on the first click and Through on the second.
	const pick = (iso: string) => {
		if (picking === "from" || !parseIsoDate(from)) {
			setFrom(iso);
			setThrough(iso);
			setPicking("through");
			return;
		}
		if (iso < from) {
			setThrough(from);
			setFrom(iso);
		} else {
			setThrough(iso);
		}
		setPicking("from");
	};

	const save = async () => {
		if (!valid || bookable.length === 0) return;
		setBusy(true);
		const inputs = bookable.map((date) => {
			const was = onRecord.get(date);
			return {
				date,
				type,
				halfDay,
				// A day on record keeps its own note unless one was typed.
				note: noteEdited || !was ? note : (was.note ?? ""),
			};
		});
		const { done, error } = await record.mutateAsync({ projectId: project.id, inputs });
		setBusy(false);
		if (error === null) {
			toast.success(done === 1 ? "Time off booked" : `${done} days booked`);
			onClose();
		} else if (done === 0) {
			toast.error(describeError(error, "Failed to book time off"));
		} else {
			// Nothing is rolled back: what was saved stands, and saving again books the rest.
			toast.error(
				`${done} of ${inputs.length} days saved — ${describeError(error, "the rest failed")}`,
			);
		}
	};

	const removeAll = async () => {
		const absenceIds = [...onRecord.values()].map((a) => a.id);
		setBusy(true);
		const { done, error } = await remove.mutateAsync({ projectId: project.id, absenceIds });
		setBusy(false);
		if (error === null) {
			toast.success(done === 1 ? "Time off removed" : `${done} days removed`);
			onClose();
		} else if (done === 0) {
			toast.error(describeError(error, "Failed to remove time off"));
		} else {
			toast.error(
				`${done} of ${absenceIds.length} days removed — ${describeError(error, "the rest failed")}`,
			);
		}
	};

	// A run in flight closes the dialog itself once it is over. Closed under
	// it, the writes went on, and their close then shut the next booking.
	const close = () => {
		if (!busy) onClose();
	};

	const first = parseIsoDate(month) ?? new Date();
	const lead = (first.getDay() + 6) % 7;
	const count = daysInMonth(month);
	const monthLabel = first.toLocaleDateString("en-US", { month: "long", year: "numeric" });

	return (
		<Dialog
			open
			onClose={close}
			returnFocus={returnFocus}
			title={initial ? "Change time off" : "Book time off"}
			description="A day, half a day or a run of days the contract does not expect work on."
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

				<div className="mt-3 grid grid-cols-2 gap-3">
					<div>
						<label htmlFor={`${id}-from`} className={cn(LABEL, "block mb-[5px]")}>
							From
						</label>
						<input
							id={`${id}-from`}
							type="date"
							value={from}
							onChange={(e) => changeFrom(e.target.value)}
							className={FIELD}
						/>
					</div>
					<div>
						<label htmlFor={`${id}-through`} className={cn(LABEL, "block mb-[5px]")}>
							Through
						</label>
						<input
							id={`${id}-through`}
							type="date"
							value={through}
							min={parseIsoDate(from) ? from : undefined}
							onChange={(e) => changeThrough(e.target.value)}
							aria-invalid={range === null || tooLong ? true : undefined}
							aria-describedby={range === null || tooLong ? `${id}-range-error` : undefined}
							className={FIELD}
						/>
					</div>
				</div>
				{(range === null || tooLong) && (
					<p id={`${id}-range-error`} className="mt-1.5 text-xs text-destructive-ink">
						{tooLong
							? "Book at most a year at a time."
							: parseIsoDate(from) && parseIsoDate(through)
								? "Through is before From."
								: "Enter both days."}
					</p>
				)}

				<div className="mt-3.5 rounded-[18px] p-3 bg-secondary">
					<div className="flex justify-between items-center text-[12.5px] font-extrabold mb-1.5">
						<button
							type="button"
							onClick={() => setMonth((m) => addMonths(m, -1))}
							aria-label="Previous month"
							className="grid place-items-center w-7 h-7 rounded-full hover:bg-sidebar-accent focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
						>
							<ChevronLeft className="w-3.5 h-3.5" aria-hidden="true" />
						</button>
						<span aria-live="polite">{monthLabel}</span>
						<button
							type="button"
							onClick={() => setMonth((m) => addMonths(m, 1))}
							aria-label="Next month"
							className="grid place-items-center w-7 h-7 rounded-full hover:bg-sidebar-accent focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
						>
							<ChevronRight className="w-3.5 h-3.5" aria-hidden="true" />
						</button>
					</div>
					<div className="grid grid-cols-7 gap-[3px] text-center text-[11.5px] font-bold font-mono">
						{WEEKDAYS.map((d) => (
							<div
								key={d}
								aria-hidden="true"
								className="font-body text-muted-foreground text-[9px] font-bold tracking-[0.08em] pt-0.5 pb-1"
							>
								{d}
							</div>
						))}
						{Array.from({ length: lead }, (_, i) => (
							<div key={`blank-${i}`} aria-hidden="true" />
						))}
						{Array.from({ length: count }, (_, i) => {
							const iso = `${month.slice(0, 8)}${String(i + 1).padStart(2, "0")}`;
							const weekend = !isWeekdayIso(iso);
							const past = iso < todayIso;
							const isToday = iso === todayIso;
							const ring = isToday ? "shadow-[inset_0_0_0_2px_hsl(var(--accent))]" : "";
							if (weekend) {
								return (
									<div
										key={iso}
										aria-hidden="true"
										className={cn("py-1.5 rounded-[10px] text-muted-foreground font-medium", ring)}
									>
										{i + 1}
									</div>
								);
							}
							const holiday = holidays.get(iso);
							const absence = byDate.get(iso);
							const selected = valid && iso >= from && iso <= through && !holiday;
							const label = [
								longDate(iso),
								holiday ? `public holiday: ${holiday}` : null,
								absence
									? `${ABSENCE_TYPE_LABELS[absence.type]}${absence.halfDay ? ", half day" : ""} booked`
									: null,
								isToday ? "today" : null,
							]
								.filter((part): part is string => part !== null)
								.join(", ");
							return (
								<button
									key={iso}
									type="button"
									onClick={() => pick(iso)}
									aria-pressed={selected}
									aria-label={label}
									className={cn(
										"py-1.5 rounded-[10px] transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
										selected
											? "bg-accent text-accent-foreground"
											: holiday
												? TINT.holiday
												: absence
													? TINT[absence.type]
													: past
														? "text-muted-foreground hover:bg-sidebar-accent"
														: "text-foreground hover:bg-sidebar-accent",
										ring,
									)}
								>
									{i + 1}
								</button>
							);
						})}
					</div>
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
						onChange={(e) => {
							setNote(e.target.value);
							setNoteEdited(true);
						}}
						placeholder={mixedNotes ? "Different notes — typing replaces them" : "e.g. Zürich trip"}
						className={cn(FIELD, "font-body font-medium")}
					/>
				</div>

				{cost && (
					<p className="mt-2.5 text-[12.5px] font-medium text-muted-foreground" aria-live="polite">
						{cost}
					</p>
				)}

				<div className="flex flex-wrap items-center gap-2.5 mt-[18px]">
					{removable && (
						<Button
							type="button"
							variant="ghost"
							size="sm"
							className="text-destructive hover:text-destructive"
							disabled={busy}
							onClick={() => void removeAll()}
						>
							{onRecord.size === 1 ? "Remove" : `Remove ${onRecord.size} days`}
						</Button>
					)}
					<div className="ml-auto flex gap-2.5">
						<Button type="button" variant="secondary" size="sm" onClick={close} disabled={busy}>
							Cancel
						</Button>
						<Button
							type="submit"
							size="sm"
							disabled={busy || !valid || bookable.length === 0 || holidaysLoading || rangeLoading}
						>
							{busy ? "Saving…" : "Save"}
						</Button>
					</div>
				</div>
			</form>
		</Dialog>
	);
}
