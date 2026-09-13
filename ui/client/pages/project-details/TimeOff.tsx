/**
 * TimeOff — the rail's "Time off · upcoming" on a day job, contract or not:
 * the absences still to come and the region's public holidays in one list by
 * date, a run of weekday absences of one type as one row ("Mon Oct 5 – Fri
 * Oct 9 · Vacation · 5 days"), and the calendar year's tally. The month grid
 * is not here: it is the date picker inside the booking dialog (Decision 10).
 *
 * An absence row opens the booking dialog on its days; a holiday has nothing
 * to book, so its row opens its week in Days instead. A date outside the
 * calendar year carries its year, since the list runs a year ahead.
 */

import { type Ref, useState } from "react";
import type { Absence, AbsenceType } from "@/entities/absence";
import { ABSENCE_TYPE_LABELS, useAbsences } from "@/entities/absence";
import type { ProjectWithDuration } from "@/entities/project";
import { useHolidayRegions, useProjectHolidays } from "@/entities/project";
import { describeError } from "@/shared/api";
import { addIsoDays, cn } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import type { AbsenceBooking } from "./AbsenceDialog";
import { isWeekdayIso, longDate, shortDate } from "./dates";
import { LABEL, LINKISH, SUB, TINT, TINT_PILL } from "./styles";

interface AbsenceRun {
	from: string;
	through: string;
	type: AbsenceType;
	/** The absences in the run, by date. */
	absences: Absence[];
}

export interface TimeOffProps {
	project: ProjectWithDuration;
	todayIso: string;
	/** "+ Book": the dialog on its default day. */
	onBook: () => void;
	/** An absence row: the dialog on the run's days, with what they share. */
	onOpenAbsence: (booking: AbsenceBooking) => void;
	/** A holiday row: its week in Days. */
	onOpenWeek: (dateIso: string) => void;
	/** "+ Book" — where focus lands when a row's dialog closes on a run it removed. */
	bookButtonRef?: Ref<HTMLButtonElement>;
}

/** Rows shown before "Show all". */
const SHOWN = 6;
const TYPES: AbsenceType[] = ["vacation", "sick", "other"];

type Entry = ({ kind: "absence" } & AbsenceRun) | { kind: "holiday"; date: string; name: string };

/** "21", "½", "2½" — days counted in halves. */
function days(n: number): string {
	const whole = Math.floor(n);
	const half = n - whole >= 0.5 ? "½" : "";
	return whole === 0 ? half || "0" : `${whole}${half}`;
}

function dayCount(run: AbsenceRun): number {
	return run.absences.reduce((sum, a) => sum + (a.halfDay ? 0.5 : 1), 0);
}

/** The next day a run of absences could continue on: skips weekends and public holidays. */
function nextWorkday(iso: string, holidays: Set<string>): string {
	let next = addIsoDays(iso, 1);
	for (let i = 0; i < 14 && (!isWeekdayIso(next) || holidays.has(next)); i += 1) {
		next = addIsoDays(next, 1);
	}
	return next;
}

/** Consecutive weekday absences of one type as one run; anything else its own. */
function runsOf(absences: Absence[], holidays: Set<string>): AbsenceRun[] {
	const runs: AbsenceRun[] = [];
	for (const absence of [...absences].sort((a, b) => a.date.localeCompare(b.date))) {
		const run = runs[runs.length - 1];
		const last = run?.absences[run.absences.length - 1];
		if (
			run &&
			last &&
			run.type === absence.type &&
			isWeekdayIso(last.date) &&
			isWeekdayIso(absence.date) &&
			nextWorkday(last.date, holidays) === absence.date
		) {
			run.absences.push(absence);
			run.through = absence.date;
		} else {
			runs.push({
				from: absence.date,
				through: absence.date,
				type: absence.type,
				absences: [absence],
			});
		}
	}
	return runs;
}

/**
 * A run as the dialog opens on it: its days, its type, half day only when
 * every day is one, and the note only when every day shares it — else the
 * field starts empty and each day keeps its own unless one is typed.
 */
function bookingOf(run: AbsenceRun): AbsenceBooking {
	const notes = new Set(run.absences.map((a) => a.note ?? ""));
	return {
		from: run.from,
		through: run.through,
		initial: {
			type: run.type,
			halfDay: run.absences.every((a) => a.halfDay),
			note: notes.size === 1 ? [...notes][0] : "",
		},
	};
}

/** "2026: 21 d vacation booked · ½ d sick" — half days count a half. */
function tally(absences: Absence[], year: number): string {
	const inYear = absences.filter((a) => a.date.startsWith(`${year}-`));
	const parts = TYPES.map((type) => {
		const n = inYear.filter((a) => a.type === type).reduce((s, a) => s + (a.halfDay ? 0.5 : 1), 0);
		return n > 0 ? `${days(n)} d ${type}` : null;
	}).filter((part): part is string => part !== null);
	if (parts.length === 0) return `Nothing booked yet in ${year}`;
	parts[0] = `${parts[0]} booked`;
	return `${year}: ${parts.join(" · ")}`;
}

export function TimeOff({
	project,
	todayIso,
	onBook,
	onOpenAbsence,
	onOpenWeek,
	bookButtonRef,
}: TimeOffProps) {
	const [expanded, setExpanded] = useState(false);
	const year = Number(todayIso.slice(0, 4));
	// "Fri Jan 1, 2027" under "Fri Dec 25": the list crosses into next year.
	const dateOf = (iso: string) => (iso.startsWith(`${year}-`) ? shortDate(iso) : longDate(iso));
	// One read covers both the year's tally and a year ahead of upcoming days.
	const {
		data: absences,
		isLoading,
		error,
	} = useAbsences(project.id, { start: `${year}-01-01`, end: addIsoDays(todayIso, 365) });
	const { data: thisYear } = useProjectHolidays(project.id, year);
	const { data: nextYear } = useProjectHolidays(project.id, year + 1);
	const { data: regions } = useHolidayRegions();

	const contract = project.contract;
	const holidays = [...(thisYear ?? []), ...(nextYear ?? [])];
	const holidayDates = new Set(holidays.map((h) => h.date));
	const country = regions?.find((r) => r.code === contract?.holidayCountry);
	const regionName = contract?.holidaySubdivision
		? (country?.subdivisions.find((s) => s.code === contract.holidaySubdivision)?.name ??
			contract.holidaySubdivision)
		: (country?.name ?? contract?.holidayCountry);

	const entries: Entry[] = [
		...runsOf(absences ?? [], holidayDates)
			.filter((run) => run.through >= todayIso)
			.map((run): Entry => ({ kind: "absence", ...run })),
		...holidays
			.filter((h) => h.date >= todayIso && isWeekdayIso(h.date))
			.map((h): Entry => ({ kind: "holiday", date: h.date, name: h.name })),
	].sort((a, b) => {
		const da = a.kind === "absence" ? a.from : a.date;
		const db = b.kind === "absence" ? b.from : b.date;
		if (da !== db) return da.localeCompare(db);
		return a.kind === "holiday" ? -1 : 1;
	});
	const visible = expanded ? entries : entries.slice(0, SHOWN);
	const tomorrow = addIsoDays(todayIso, 1);

	return (
		<Panel role="region" aria-label="Time off" padding="px-6 py-[22px]">
			<div className="flex items-baseline gap-x-3 gap-y-2 flex-wrap">
				<h3 className={LABEL}>
					Time off <span className={SUB}>upcoming</span>
				</h3>
				<button
					ref={bookButtonRef}
					type="button"
					onClick={onBook}
					className={cn(LINKISH, "ml-auto")}
				>
					+ Book
				</button>
			</div>

			{error ? (
				<p role="alert" className="mt-2.5 text-[12.5px] text-destructive-ink">
					{describeError(error, "Could not load the time off")}
				</p>
			) : isLoading ? (
				<p className="mt-2.5 text-[12.5px] text-muted-foreground">Loading…</p>
			) : entries.length === 0 ? (
				<p className="mt-2.5 text-[12.5px] text-muted-foreground font-medium leading-normal">
					Nothing coming up.
				</p>
			) : (
				<ul className="mt-2.5 flex flex-col">
					{visible.map((entry, i) => {
						const start = entry.kind === "absence" ? entry.from : entry.date;
						const prefix =
							i === 0 && start === todayIso
								? "Today · "
								: i === 0 && start === tomorrow
									? "Tomorrow · "
									: "";
						let when: string;
						let what: string;
						let tint: keyof typeof TINT;
						if (entry.kind === "holiday") {
							when = dateOf(entry.date);
							what = `${entry.name} · public holiday${regionName ? ` · ${regionName}` : ""}`;
							tint = "holiday";
						} else {
							const single = entry.absences.length === 1;
							const first = entry.absences[0];
							const notes = new Set(entry.absences.map((a) => a.note ?? ""));
							const note = notes.size === 1 ? [...notes][0] : "";
							const count = dayCount(entry);
							when = single
								? dateOf(entry.from)
								: `${dateOf(entry.from)} – ${dateOf(entry.through)}`;
							what = [
								`${ABSENCE_TYPE_LABELS[entry.type]}${single && first.halfDay ? " ½" : ""}`,
								single ? null : `${days(count)} day${count <= 1 ? "" : "s"}`,
								note || null,
							]
								.filter((part): part is string => part !== null)
								.join(" · ");
							tint = entry.type;
						}
						return (
							<li key={`${entry.kind}-${start}`} className="border-t border-border">
								<button
									type="button"
									onClick={() =>
										entry.kind === "holiday"
											? onOpenWeek(entry.date)
											: onOpenAbsence(bookingOf(entry))
									}
									title={entry.kind === "holiday" ? "Open its week" : "Change or remove"}
									className="w-full grid grid-cols-[minmax(0,1fr)_auto] gap-2 items-center py-[9px] px-1.5 -mx-1.5 text-left text-[12.5px] rounded-xl hover:bg-secondary transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
								>
									<span className="min-w-0 text-foreground">
										<b className="font-extrabold">
											{prefix}
											{when}
										</b>
										<small className="block text-muted-foreground text-[11.5px] font-medium">
											{what}
										</small>
									</span>
									<span className={cn(TINT_PILL, TINT[tint])}>{tint}</span>
								</button>
							</li>
						);
					})}
				</ul>
			)}
			{entries.length > SHOWN && (
				<button
					type="button"
					onClick={() => setExpanded((e) => !e)}
					className={cn(LINKISH, "mt-1.5")}
				>
					{expanded ? "Show fewer" : `Show all ${entries.length}`}
				</button>
			)}

			<p className="mt-2.5 pt-2.5 border-t border-border text-[12.5px] leading-[1.6] font-medium text-muted-foreground">
				{absences ? tally(absences, year) : "…"}
			</p>
			{!contract?.holidayCountry && (
				<p className="mt-1 text-xs text-muted-foreground font-medium leading-normal">
					Public holidays appear once the contract has a region.
				</p>
			)}
		</Panel>
	);
}
