/**
 * Project Details Page — the identity on the sky, the standing, the open
 * week's days and the ledger of earlier weeks, with the contract (or the
 * goal), the time off and the quiet facts in a rail
 * (docs/project-page-roadmap.md, "The page").
 *
 * The page owns the reads the panels share: `/contract/week` for the open
 * week, the current week (the balance is pinned to today) and the next
 * (for "then Mon 6.7 h"), the ledger, the sessions and the running timer.
 * The open week is the URL's (`?week=`), so a ledger row, ‹ ›, a holiday in
 * the time off and a link all move the same navigator. It also owns the
 * booking dialog, which every "Book time off" and "Change" opens, and knows
 * where focus goes when a save takes away the control that opened it.
 */

import { ChevronLeft, Clock } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useParams } from "react-router";
import {
	type ContractWeek,
	LoadingSpinner,
	type ProjectFormAutoFocusField,
	useContractWeek,
	useProject,
	useProjectLedger,
} from "@/entities/project";
import { useSessions } from "@/entities/session";
import {
	addIsoDays,
	mondayOfIso,
	parseUtcIso,
	todayIso as readToday,
	toIsoDate,
} from "@/shared/lib";
import { type AbsenceBooking, AbsenceDialog } from "./AbsenceDialog";
import { ContractRegister } from "./ContractRegister";
import { nextWeekdayAfter } from "./dates";
import { ProjectHeader } from "./ProjectHeader";
import { ProjectSettingsDrawer } from "./ProjectSettingsDrawer";
import { QuietFacts } from "./QuietFacts";
import { Standing } from "./Standing";
import { TimeOff } from "./TimeOff";
import { useOpenWeek } from "./useOpenWeek";
import { useRunningBeat } from "./useRunningBeat";
import { WeekDays } from "./WeekDays";
import { WeekLedger } from "./WeekLedger";

const LEDGER_WEEKS = 8;
/**
 * While a beat runs on this project its hours move Worked, today's figure,
 * the balance and the sentence. A timer start writes nothing those reads
 * return, so the current week and the ledger poll until it stops — once a
 * minute, the live row's own granularity.
 */
const LIVE_REFETCH_MS = 60_000;

interface Booking extends AbsenceBooking {
	/** Remounts the dialog, so each opening starts from its own fields. */
	key: number;
	/** What takes focus on close when the control that opened the dialog has gone. */
	returnFocus: () => HTMLElement | null;
}

/**
 * Where "Book time off" starts: the first day after today the contract
 * expects hours on, in this week or the next; else the first weekday after
 * today with nothing off on it — not a day already booked.
 */
function nextDueDay(todayIso: string, weeks: (ContractWeek | undefined)[]): string {
	const days = weeks.flatMap((week) => week?.days ?? []);
	const due = days.find((day) => day.date > todayIso && day.expected > 0);
	if (due) return due.date;
	const off = new Set(days.filter((day) => day.absence || day.holiday).map((day) => day.date));
	let day = nextWeekdayAfter(todayIso);
	while (off.has(day)) day = nextWeekdayAfter(day);
	return day;
}

export default function ProjectDetails() {
	const { projectId } = useParams<{ projectId: string }>();
	const today = readToday();
	const thisMonday = mondayOfIso(today);
	const [weekOf, setWeekOf] = useOpenWeek(today);
	const [ledgerWeeks, setLedgerWeeks] = useState(LEDGER_WEEKS);
	const [settingsOpen, setSettingsOpen] = useState(false);
	const [settingsFocus, setSettingsFocus] = useState<ProjectFormAutoFocusField>("name");
	const [booking, setBooking] = useState<Booking | null>(null);
	const bookings = useRef(0);
	// "Change contract…" in the settings form lands on the register's own
	// button: terms are edited there, not in the form.
	const changeContractButtonRef = useRef<HTMLButtonElement>(null);
	// A ledger row opens its week in the Days panel, which may be a screen up.
	const daysRef = useRef<HTMLDivElement>(null);
	const timeOffBookRef = useRef<HTMLButtonElement>(null);

	const { data: project, isLoading: projectLoading, error: projectError } = useProject(projectId);
	const { data: sessions } = useSessions(projectId);
	const running = useRunningBeat(projectId);
	const poll = running !== null ? LIVE_REFETCH_MS : false;

	const governedProject = project?.kind === "day_job" && project.contract !== undefined;
	const openWeekQuery = useContractWeek(projectId, weekOf, { enabled: governedProject });
	const currentWeekQuery = useContractWeek(projectId, thisMonday, {
		enabled: governedProject,
		refetchInterval: poll,
	});
	const { data: nextWeek } = useContractWeek(projectId, addIsoDays(thisMonday, 7), {
		enabled: governedProject,
	});
	const ledgerQuery = useProjectLedger(projectId, ledgerWeeks, { refetchInterval: poll });
	const ledger = ledgerQuery.data;
	// On the current week the open week is the current week's query, polled with it.
	const openQuery = weekOf === thisMonday ? currentWeekQuery : openWeekQuery;

	const openSettings = (field: ProjectFormAutoFocusField) => {
		setSettingsFocus(field);
		setSettingsOpen(true);
	};

	// Called by the drawer once it has closed and released focus.
	const handleChangeContract = () => {
		const button = changeContractButtonRef.current;
		button?.scrollIntoView?.({ behavior: "smooth", block: "center" });
		button?.focus();
	};

	const openBooking = (next: AbsenceBooking, returnFocus: () => HTMLElement | null) => {
		bookings.current += 1;
		setBooking({ ...next, key: bookings.current, returnFocus });
	};

	// A save can take away the control that opened the dialog — "Book time off
	// on Wed 16" becomes "Change", a removed run leaves Time off — and focus
	// then lands on what replaced it rather than on <body>.
	const dayControl = (date: string) => () => {
		const row = daysRef.current?.querySelector(`[data-day="${date}"]`);
		return (
			row?.querySelector<HTMLElement>("[data-booking]") ??
			row?.querySelector<HTMLElement>("button") ??
			daysRef.current?.querySelector<HTMLElement>("button") ??
			null
		);
	};
	const timeOffBook = () => timeOffBookRef.current;

	const bookFromDefault = () =>
		openBooking({ from: nextDueDay(today, [currentWeekQuery.data, nextWeek]) }, timeOffBook);

	const openWeekFromLedger = (week: string) => {
		setWeekOf(week);
		daysRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
	};

	if (projectLoading) {
		return <LoadingSpinner message="Loading project..." />;
	}

	if (projectError || !project) {
		return (
			<div className="max-w-3xl mx-auto px-6 py-12">
				<div className="text-center py-20">
					<Clock className="w-10 h-10 text-muted-foreground/30 mx-auto mb-3" />
					<p className="text-muted-foreground text-sm">Project not found</p>
				</div>
			</div>
		);
	}

	const sessionList = sessions ?? [];
	const ledgerWeek = ledger?.weeks.find((w) => w.weekOf === weekOf);
	const firstStart = sessionList.map((s) => s.startTime).sort()[0];
	const firstTrackedIso = firstStart ? toIsoDate(parseUtcIso(firstStart)) : undefined;

	return (
		<div className="max-w-5xl mx-auto px-4 sm:px-6 pb-24">
			{/* Mobile back-link breadcrumb. Hidden on >= lg because the sidebar is the nav surface there. */}
			<Link
				to="/app"
				className="lg:hidden inline-flex items-center gap-1 text-xs font-bold text-foreground/70 pt-3 pb-1 hover:text-foreground transition-colors"
			>
				<ChevronLeft className="w-3.5 h-3.5" aria-hidden="true" />
				Back
			</Link>

			<div className="pt-2 sm:pt-4">
				<ProjectHeader project={project} todayIso={today} onOpenSettings={openSettings} />
			</div>

			<div className="@container/content min-w-0">
				<div className="grid grid-cols-[minmax(0,1fr)] gap-6 mt-1 @min-[860px]/content:grid-cols-[minmax(0,1fr)_300px]">
					{/* Not a <main>: the app shell already has one, and the panels are named regions. */}
					<div className="min-w-0 flex flex-col gap-6">
						<Standing
							project={project}
							todayIso={today}
							openWeekOf={weekOf}
							currentWeek={currentWeekQuery.data}
							currentWeekError={currentWeekQuery.error}
							openWeek={openQuery.data}
							openWeekError={openQuery.error}
							nextWeek={nextWeek}
							ledger={ledger}
							ledgerLoading={ledgerQuery.isLoading}
							ledgerError={ledgerQuery.error}
							running={running !== null}
							onBookTimeOff={bookFromDefault}
							onEditGoal={() => openSettings("weeklyGoal")}
							onAddContract={() => openSettings("scheduleType")}
							onSetRegion={() => openSettings("holidayCountry")}
						/>
						<div ref={daysRef} className="scroll-mt-4">
							<WeekDays
								project={project}
								todayIso={today}
								weekOf={weekOf}
								onWeekChange={setWeekOf}
								contractWeek={openQuery.data}
								ledgerWeek={ledgerWeek}
								running={running}
								onChangeAbsence={(date, absence) =>
									openBooking(
										{
											from: date,
											initial: {
												type: absence.type,
												halfDay: absence.halfDay,
												note: absence.note,
											},
										},
										dayControl(date),
									)
								}
								onBookTimeOff={(date) => openBooking({ from: date }, dayControl(date))}
							/>
						</div>
						<WeekLedger
							project={project}
							todayIso={today}
							ledger={ledger}
							isLoading={ledgerQuery.isLoading}
							error={ledgerQuery.error}
							weeks={ledgerWeeks}
							onShowMore={() => setLedgerWeeks((n) => Math.min(n + 5, 104))}
							onOpenWeek={openWeekFromLedger}
							openWeekOf={weekOf}
							sessionCount={sessionList.length}
						/>
					</div>

					<aside className="flex flex-col gap-6 @min-[860px]/content:sticky @min-[860px]/content:top-4 @min-[860px]/content:self-start">
						<ContractRegister
							project={project}
							todayIso={today}
							firstTrackedIso={firstTrackedIso}
							onOpenSettings={openSettings}
							changeButtonRef={changeContractButtonRef}
						/>
						{project.kind === "day_job" && (
							<TimeOff
								project={project}
								todayIso={today}
								onBook={bookFromDefault}
								bookButtonRef={timeOffBookRef}
								onOpenAbsence={(next) => openBooking(next, timeOffBook)}
								onOpenWeek={openWeekFromLedger}
							/>
						)}
						<QuietFacts project={project} sessions={sessionList} todayIso={today} />
					</aside>
				</div>
			</div>

			<ProjectSettingsDrawer
				project={project}
				open={settingsOpen}
				onClose={() => setSettingsOpen(false)}
				autoFocusField={settingsFocus}
				onChangeContract={project.contract ? handleChangeContract : undefined}
			/>

			{/* A dialog's close shuts only the booking it was opened on. */}
			{booking && project.kind === "day_job" && (
				<AbsenceDialog
					key={booking.key}
					project={project}
					todayIso={today}
					from={booking.from}
					through={booking.through}
					initial={booking.initial}
					returnFocus={booking.returnFocus}
					onClose={() => setBooking((open) => (open?.key === booking.key ? null : open))}
				/>
			)}
		</div>
	);
}
