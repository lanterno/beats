/**
 * Project Details Page — the identity on the sky, the standing, the open
 * week's days and the ledger of earlier weeks, with the contract and the
 * absences in a rail (docs/project-page-roadmap.md, "The page").
 *
 * The page owns the reads the panels share: `/contract/week` for the open
 * week, the current week (the balance is pinned to today) and the next
 * (for "then Mon 6.7 h"), the ledger, the sessions and the running timer.
 * The open week is the URL's (`?week=`), so a ledger row, ‹ › and a link
 * all move the same navigator.
 */

import { ChevronLeft, Clock } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useParams } from "react-router";
import {
	LoadingSpinner,
	type ProjectFormAutoFocusField,
	useContractWeek,
	useProject,
	useProjectLedger,
} from "@/entities/project";
import { useSessions } from "@/entities/session";
import { addIsoDays, mondayOfIso, todayIso as readToday } from "@/shared/lib";
import { AbsenceCalendar } from "./AbsenceCalendar";
import { ContractHistoryPanel } from "./ContractHistoryPanel";
import { ProjectDangerZone } from "./ProjectDangerZone";
import { ProjectHeader } from "./ProjectHeader";
import { ProjectSettingsDrawer } from "./ProjectSettingsDrawer";
import { QuietFacts } from "./QuietFacts";
import { Standing } from "./Standing";
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

export default function ProjectDetails() {
	const { projectId } = useParams<{ projectId: string }>();
	const today = readToday();
	const thisMonday = mondayOfIso(today);
	const [weekOf, setWeekOf] = useOpenWeek(today);
	const [ledgerWeeks, setLedgerWeeks] = useState(LEDGER_WEEKS);
	const [settingsOpen, setSettingsOpen] = useState(false);
	const [settingsFocus, setSettingsFocus] = useState<ProjectFormAutoFocusField>("name");
	// "Change contract…" in the settings form lands on the history panel's
	// own button: terms are edited there, not in the form.
	const changeContractButtonRef = useRef<HTMLButtonElement>(null);
	// "Book time off" and a day's "Change" bring the reader to the absences,
	// which stay in the rail until Phase 3b's dialog.
	const absencesRef = useRef<HTMLDivElement>(null);
	// A ledger row opens its week in the Days panel, which may be a screen up.
	const daysRef = useRef<HTMLDivElement>(null);

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

	const scrollToAbsences = () => {
		absencesRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
	};

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
							onBookTimeOff={scrollToAbsences}
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
								onChangeAbsence={scrollToAbsences}
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
						{project.kind === "day_job" && (
							<ContractHistoryPanel
								project={project}
								onOpenSettings={() => openSettings("scheduleType")}
								changeButtonRef={changeContractButtonRef}
							/>
						)}
						{project.kind === "day_job" && project.contract && (
							<div ref={absencesRef} className="scroll-mt-4">
								<AbsenceCalendar projectId={project.id} />
							</div>
						)}
						<QuietFacts project={project} sessions={sessionList} todayIso={today} />
					</aside>
				</div>

				<ProjectDangerZone
					projectId={project.id}
					projectName={project.name}
					archived={project.archived}
				/>
			</div>

			<ProjectSettingsDrawer
				project={project}
				open={settingsOpen}
				onClose={() => setSettingsOpen(false)}
				autoFocusField={settingsFocus}
				onChangeContract={project.contract ? handleChangeContract : undefined}
			/>
		</div>
	);
}
