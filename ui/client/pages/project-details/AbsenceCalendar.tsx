/**
 * AbsenceCalendar — a month of a day job, with the region's public
 * holidays pre-marked and the recorded absences coloured by type. A
 * weekday is a button: click one to record vacation / sick / other (half
 * day or whole, with a note); click a day that has one to change or
 * remove it. Weekends and holidays are not buttons — the contract owes
 * nothing on them, so there is nothing to record.
 *
 * Types are told apart by a text label as well as a colour, and every
 * button's name says the date and what is on it, so the grid reads the
 * same by keyboard and screen reader as by mouse.
 */

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import type { Absence, AbsenceType } from "@/entities/absence";
import {
	ABSENCE_TYPE_LABELS,
	useAbsences,
	useRecordAbsence,
	useRemoveAbsence,
} from "@/entities/absence";
import { useProjectHolidays } from "@/entities/project";
import { describeError } from "@/shared/api";
import { parseIsoDate, todayIso, toIsoDate } from "@/shared/lib";
import { Button, Dialog } from "@/shared/ui";

interface AbsenceCalendarProps {
	projectId: string;
	/** The month to open on; defaults to the current one. Any day of the month will do. */
	initialMonth?: Date;
}

const WEEKDAY_HEADERS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

const ABSENCE_STYLES: Record<AbsenceType, string> = {
	vacation: "bg-accent/20 border-accent/50 text-foreground",
	sick: "bg-destructive/15 border-destructive/50 text-foreground",
	other: "bg-secondary border-muted-foreground/40 text-foreground",
};

const ABSENCE_SHORT: Record<AbsenceType, string> = {
	vacation: "Vac",
	sick: "Sick",
	other: "Other",
};

function firstOfMonth(d: Date): Date {
	return new Date(d.getFullYear(), d.getMonth(), 1, 12, 0, 0, 0);
}

function addMonths(d: Date, n: number): Date {
	return new Date(d.getFullYear(), d.getMonth() + n, 1, 12, 0, 0, 0);
}

function daysInMonth(d: Date): number {
	return new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
}

function longDate(iso: string): string {
	const d = parseIsoDate(iso);
	return d
		? d.toLocaleDateString(undefined, {
				weekday: "long",
				day: "numeric",
				month: "long",
				year: "numeric",
			})
		: iso;
}

export function AbsenceCalendar({ projectId, initialMonth }: AbsenceCalendarProps) {
	const [month, setMonth] = useState(() => firstOfMonth(initialMonth ?? new Date()));
	const [chooser, setChooser] = useState<{ date: string; existing?: Absence } | null>(null);
	const headingId = useId();

	const count = daysInMonth(month);
	const range = {
		start: toIsoDate(month),
		end: toIsoDate(new Date(month.getFullYear(), month.getMonth(), count, 12)),
	};
	const { data: absences, error: absencesError } = useAbsences(projectId, range);
	const { data: holidays } = useProjectHolidays(projectId, month.getFullYear());
	const record = useRecordAbsence();
	const remove = useRemoveAbsence();

	const absenceByDate = new Map((absences ?? []).map((a) => [a.date, a]));
	const holidayByDate = new Map((holidays ?? []).map((h) => [h.date, h.name]));
	const today = todayIso();
	const leadingBlanks = (month.getDay() + 6) % 7;
	const monthLabel = month.toLocaleDateString(undefined, { month: "long", year: "numeric" });

	const closeChooser = () => setChooser(null);

	const handleRecord = (input: { type: AbsenceType; halfDay: boolean; note: string }) => {
		if (!chooser) return;
		record.mutate(
			{ projectId, input: { date: chooser.date, ...input } },
			{
				onSuccess: () => {
					toast.success(chooser.existing ? "Absence updated" : "Absence recorded");
					closeChooser();
				},
				onError: (err) => toast.error(describeError(err, "Failed to record absence")),
			},
		);
	};

	const handleRemove = () => {
		if (!chooser?.existing) return;
		remove.mutate(
			{ projectId, absenceId: chooser.existing.id },
			{
				onSuccess: () => {
					toast.success("Absence removed");
					closeChooser();
				},
				onError: (err) => toast.error(describeError(err, "Failed to remove absence")),
			},
		);
	};

	return (
		<section
			aria-labelledby={headingId}
			className="rounded-lg border border-border/60 bg-secondary/10 p-3"
		>
			<header className="flex items-center gap-1.5 mb-2">
				<h3
					id={headingId}
					className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground"
				>
					Absences
				</h3>
				<div className="ml-auto flex items-center gap-1">
					<button
						type="button"
						onClick={() => setMonth((m) => addMonths(m, -1))}
						aria-label="Previous month"
						className="p-1 rounded text-muted-foreground/70 hover:text-foreground hover:bg-secondary/60 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
					>
						<ChevronLeft className="w-4 h-4" />
					</button>
					<span
						className="text-xs text-foreground tabular-nums min-w-28 text-center"
						aria-live="polite"
					>
						{monthLabel}
					</span>
					<button
						type="button"
						onClick={() => setMonth((m) => addMonths(m, 1))}
						aria-label="Next month"
						className="p-1 rounded text-muted-foreground/70 hover:text-foreground hover:bg-secondary/60 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
					>
						<ChevronRight className="w-4 h-4" />
					</button>
				</div>
			</header>

			<div className="grid grid-cols-7 gap-1 text-[10px] uppercase tracking-wider text-muted-foreground/70 mb-1">
				{WEEKDAY_HEADERS.map((d) => (
					<div key={d} className="text-center" aria-hidden="true">
						{d}
					</div>
				))}
			</div>
			<div className="grid grid-cols-7 gap-1">
				{Array.from({ length: leadingBlanks }, (_, i) => (
					<div key={`blank-${i}`} aria-hidden="true" />
				))}
				{Array.from({ length: count }, (_, i) => {
					const day = i + 1;
					const date = new Date(month.getFullYear(), month.getMonth(), day, 12);
					const iso = toIsoDate(date);
					const weekend = date.getDay() === 0 || date.getDay() === 6;
					const holiday = holidayByDate.get(iso);
					const absence = absenceByDate.get(iso);
					const isToday = iso === today;
					const ring = isToday ? "ring-2 ring-accent/60" : "";

					if (weekend) {
						return (
							<div
								key={iso}
								className={`min-h-12 rounded-md px-1.5 py-1 text-xs text-muted-foreground/40 bg-background/20 ${ring}`}
							>
								<span aria-hidden="true">{day}</span>
								<span className="sr-only">{longDate(iso)}, weekend</span>
							</div>
						);
					}
					if (holiday) {
						return (
							<div
								key={iso}
								className={`min-h-12 rounded-md px-1.5 py-1 text-xs border border-success/40 bg-success/10 ${ring}`}
								title={holiday}
							>
								<span className="text-foreground tabular-nums" aria-hidden="true">
									{day}
								</span>
								<span className="sr-only">{longDate(iso)}, public holiday: </span>
								<span className="block text-[10px] leading-tight text-success truncate">
									{holiday}
								</span>
							</div>
						);
					}
					const label = absence
						? `${longDate(iso)}: ${ABSENCE_TYPE_LABELS[absence.type]}${
								absence.halfDay ? ", half day" : ""
							}${absence.note ? ` — ${absence.note}` : ""}. Change or remove`
						: `${longDate(iso)}: record an absence`;
					return (
						<button
							key={iso}
							type="button"
							onClick={() => setChooser({ date: iso, existing: absence })}
							aria-label={label}
							className={`min-h-12 rounded-md px-1.5 py-1 text-left text-xs border transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40 ${
								absence
									? ABSENCE_STYLES[absence.type]
									: "border-transparent bg-background/40 hover:bg-secondary/60"
							} ${ring}`}
						>
							<span className="tabular-nums">{day}</span>
							{absence && (
								<span className="block text-[10px] leading-tight font-medium">
									{ABSENCE_SHORT[absence.type]}
									{absence.halfDay ? " ½" : ""}
								</span>
							)}
						</button>
					);
				})}
			</div>

			<ul
				className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted-foreground"
				aria-label="Legend"
			>
				<li className="flex items-center gap-1">
					<span className="inline-block w-2.5 h-2.5 rounded-sm bg-accent/40" aria-hidden="true" />
					Vacation
				</li>
				<li className="flex items-center gap-1">
					<span
						className="inline-block w-2.5 h-2.5 rounded-sm bg-destructive/40"
						aria-hidden="true"
					/>
					Sick
				</li>
				<li className="flex items-center gap-1">
					<span
						className="inline-block w-2.5 h-2.5 rounded-sm bg-secondary border border-muted-foreground/40"
						aria-hidden="true"
					/>
					Other
				</li>
				<li className="flex items-center gap-1">
					<span className="inline-block w-2.5 h-2.5 rounded-sm bg-success/30" aria-hidden="true" />
					Public holiday
				</li>
				<li>½ = half day</li>
			</ul>
			{absencesError && (
				<p className="mt-2 text-xs text-destructive" role="alert">
					{describeError(absencesError, "Could not load absences")}
				</p>
			)}

			{chooser && (
				<AbsenceDialog
					key={chooser.date}
					date={chooser.date}
					existing={chooser.existing}
					submitting={record.isPending || remove.isPending}
					onSave={handleRecord}
					onRemove={chooser.existing ? handleRemove : undefined}
					onClose={closeChooser}
				/>
			)}
		</section>
	);
}

interface AbsenceDialogProps {
	date: string;
	existing?: Absence;
	submitting: boolean;
	onSave: (input: { type: AbsenceType; halfDay: boolean; note: string }) => void;
	onRemove?: () => void;
	onClose: () => void;
}

const ABSENCE_TYPES: AbsenceType[] = ["vacation", "sick", "other"];

function AbsenceDialog({
	date,
	existing,
	submitting,
	onSave,
	onRemove,
	onClose,
}: AbsenceDialogProps) {
	const [type, setType] = useState<AbsenceType>(existing?.type ?? "vacation");
	const [halfDay, setHalfDay] = useState(existing?.halfDay ?? false);
	const [note, setNote] = useState(existing?.note ?? "");
	const id = useId();

	return (
		<Dialog
			open
			onClose={onClose}
			title={longDate(date)}
			description={
				existing ? "Change this absence, or remove it." : "Record an absence on this day."
			}
			contentClassName="sm:w-full sm:max-w-sm"
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					onSave({ type, halfDay, note });
				}}
				className="space-y-3"
			>
				<fieldset>
					<legend
						id={`${id}-type`}
						className="block text-muted-foreground text-xs uppercase tracking-[0.12em] mb-1.5"
					>
						Type
					</legend>
					<div className="flex gap-2" role="radiogroup" aria-labelledby={`${id}-type`}>
						{ABSENCE_TYPES.map((t) => {
							const selected = type === t;
							return (
								<label
									key={t}
									className={`flex-1 flex items-center gap-2 rounded-md border px-3 py-2 text-sm cursor-pointer transition-colors ${
										selected
											? "border-accent/60 bg-accent/10"
											: "border-input hover:bg-secondary/40"
									}`}
								>
									<input
										type="radio"
										name={`${id}-type`}
										value={t}
										checked={selected}
										onChange={() => setType(t)}
										className="shrink-0"
									/>
									{ABSENCE_TYPE_LABELS[t]}
								</label>
							);
						})}
					</div>
				</fieldset>
				<label className="flex items-center gap-2 text-sm text-foreground">
					<input type="checkbox" checked={halfDay} onChange={(e) => setHalfDay(e.target.checked)} />
					Half day
				</label>
				<div>
					<label
						htmlFor={`${id}-note`}
						className="block text-muted-foreground text-xs uppercase tracking-[0.12em] mb-1.5"
					>
						Note (optional)
					</label>
					<input
						id={`${id}-note`}
						value={note}
						onChange={(e) => setNote(e.target.value)}
						placeholder="e.g. Dentist"
						className="w-full rounded-md border border-input bg-background py-2 px-3 text-base text-foreground focus:outline-hidden focus:ring-2 focus:ring-accent/20 focus:border-accent/40"
					/>
				</div>
				<div className="flex gap-2 pt-1">
					<Button type="submit" disabled={submitting} className="flex-1">
						{submitting ? "Saving…" : existing ? "Save changes" : "Record absence"}
					</Button>
					{onRemove && (
						<Button type="button" variant="destructive" onClick={onRemove} disabled={submitting}>
							Remove
						</Button>
					)}
					<Button type="button" variant="outline" onClick={onClose}>
						Cancel
					</Button>
				</div>
			</form>
		</Dialog>
	);
}
