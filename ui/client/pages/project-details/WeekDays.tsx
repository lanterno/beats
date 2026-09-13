/**
 * WeekDays — the open week's seven days, once: each weekday with what the
 * contract expected of it, what was worked and its sessions underneath;
 * today open, the others one line that opens on click. Holidays and
 * absences sit on the day they cost. The running beat is a live row on
 * today. Older weeks are reached with ‹ › (the open week is in the URL).
 *
 * A day's figure is the API's — `/contract/week` on a governed week, the
 * ledger elsewhere — so it agrees with the standing above and the ledger
 * below; the sessions are grouped by the same local-start-day rule
 * (`groupSessionsByLocalDay`), so they add up to it.
 */

import { ChevronLeft, ChevronRight, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ABSENCE_TYPE_LABELS } from "@/entities/absence";
import { useProjectGitActivityByWeek } from "@/entities/github";
import { useFocusScores } from "@/entities/intelligence";
import { useProjectPlannedByWeek } from "@/entities/planning";
import type {
	ContractWeek,
	LedgerNoteKind,
	LedgerWeek,
	ProjectWithDuration,
} from "@/entities/project";
import { balanceTone, useProjects, weekNumber, weekRange } from "@/entities/project";
import type { Session } from "@/entities/session";
import {
	groupSessionsByLocalDay,
	SessionEditForm,
	useDeleteSession,
	useSessions,
	useUpdateSession,
} from "@/entities/session";
import { describeError } from "@/shared/api";
import { addIsoDays, cn, getDayName, mondayOfIso, parseIsoDate, parseUtcIso } from "@/shared/lib";
import { Button, Panel } from "@/shared/ui";
import { clock, hours1, hoursMinutes } from "./dates";
import { LABEL, LINKISH, LIVE_DOT, NAV_BUTTON, SUB, TINT, TINT_PILL, TONE } from "./styles";
import type { RunningBeat } from "./useRunningBeat";
import { useNow } from "./useRunningBeat";

export interface WeekDaysProps {
	project: ProjectWithDuration;
	todayIso: string;
	/** The open week's Monday. */
	weekOf: string;
	onWeekChange: (weekOf: string) => void;
	/** `/contract/week` for the open week, on a day job with a contract. */
	contractWeek?: ContractWeek;
	/** The ledger's week, for a day's figure where the contract does not govern. */
	ledgerWeek?: LedgerWeek;
	/** The timer, when it runs on this project. */
	running: RunningBeat | null;
	/** "Change" on a day off: brings the reader to the absences. */
	onChangeAbsence: () => void;
}

interface DayModel {
	date: string;
	/** "Mon". */
	name: string;
	/** "7", or "12–13" for the folded weekend. */
	number: string;
	sessions: Session[];
	live: boolean;
	/** Hours. */
	worked: number;
	/** Hours the contract expected; undefined off a governed week. */
	expected?: number;
	off?: { kind: LedgerNoteKind; label: string; changeable: boolean };
	isToday: boolean;
}

const ROW =
	"grid grid-cols-[124px_minmax(0,1fr)_auto] @max-[560px]/content:grid-cols-[78px_minmax(0,1fr)_auto] gap-3 @max-[560px]/content:gap-2 items-center px-3 @max-[560px]/content:px-2 py-[9px] rounded-2xl -mx-1.5 my-0.5";
/**
 * The day's toggle: a real button over the day's name whose ::after stretches
 * across the row, so a click anywhere on the row opens it while "Change" (a
 * sibling, lifted above it) stays its own control — a button cannot hold one.
 */
const TOGGLE =
	"text-left cursor-pointer rounded-2xl focus-visible:outline-hidden after:absolute after:inset-0 after:rounded-2xl focus-visible:after:ring-2 focus-visible:after:ring-ring";
const OP =
	"grid place-items-center w-6 h-6 rounded-full text-muted-foreground hover:bg-sidebar-accent hover:text-foreground transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

function dayNumber(iso: string): string {
	return String(parseIsoDate(iso)?.getDate() ?? "");
}

function isoOfTimestamp(timestamp: string): string {
	const d = parseUtcIso(timestamp);
	const y = d.getFullYear();
	const m = String(d.getMonth() + 1).padStart(2, "0");
	const day = String(d.getDate()).padStart(2, "0");
	return `${y}-${m}-${day}`;
}

/** The seven days as rows, Saturday and Sunday folded into one when both are empty. */
function buildDays(
	weekOf: string,
	todayIso: string,
	sessions: Session[],
	contractWeek: ContractWeek | undefined,
	ledgerWeek: LedgerWeek | undefined,
	running: RunningBeat | null,
	now: number,
): DayModel[] {
	const governed = contractWeek?.expected !== undefined;
	const byDay = groupSessionsByLocalDay(sessions, weekOf);
	const liveDate = running ? isoOfTimestamp(running.since) : null;
	const liveHours = running
		? Math.max(0, now - parseUtcIso(running.since).getTime()) / 3_600_000
		: 0;

	const days: DayModel[] = byDay.map((day, i) => {
		const contractDay = contractWeek?.days[i];
		const live = liveDate === day.date;
		const worked =
			contractDay?.worked ?? ledgerWeek?.days[i] ?? day.totalMinutes / 60 + (live ? liveHours : 0);
		let off: DayModel["off"];
		if (contractDay?.holiday) {
			off = { kind: "holiday", label: contractDay.holiday, changeable: false };
		} else if (contractDay?.absence) {
			const a = contractDay.absence;
			off = {
				kind: a.type,
				label: `${ABSENCE_TYPE_LABELS[a.type]}${a.halfDay ? " ½" : ""}${a.note ? ` · ${a.note}` : ""}`,
				changeable: true,
			};
		}
		return {
			date: day.date,
			name: getDayName(parseIsoDate(day.date) ?? new Date(0), "short"),
			number: dayNumber(day.date),
			sessions: day.sessions,
			live,
			worked,
			expected: governed ? contractDay?.expected : undefined,
			off,
			isToday: day.date === todayIso,
		};
	});

	const [sat, sun] = [days[5], days[6]];
	const empty = (d: DayModel) =>
		d.sessions.length === 0 && !d.live && !d.off && !(d.expected !== undefined && d.expected > 0);
	// Today keeps its own row, open by default, whatever the weekend holds.
	if (empty(sat) && empty(sun) && !sat.isToday && !sun.isToday) {
		return [
			...days.slice(0, 5),
			{
				...sat,
				name: "Sat–Sun",
				number: `${sat.number}–${sun.number}`,
				worked: 0,
				isToday: sat.isToday || sun.isToday,
			},
		];
	}
	return days;
}

/** "7.1 of 6.7 +0.4", "— of 6.7", "nothing expected", "7.1 h", "—". */
function Figure({ day, closed }: { day: DayModel; closed: boolean }) {
	const of = "text-muted-foreground font-medium";
	if (day.expected === undefined) {
		return day.worked > 0 ? (
			<>
				{hours1(day.worked)} <span className={of}>h</span>
			</>
		) : (
			<span className={of}>—</span>
		);
	}
	if (day.expected <= 0) {
		return day.worked > 0 ? (
			<>
				{hours1(day.worked)} <span className={of}>h · nothing expected</span>
			</>
		) : (
			<span className={of}>nothing expected</span>
		);
	}
	if (day.worked <= 0) {
		return (
			<span className={of}>
				— of {hours1(day.expected)}
				<span className="inline-block min-w-[3.2em]" />
			</span>
		);
	}
	const delta = day.worked - day.expected;
	const tone = balanceTone(delta);
	return (
		<>
			{hours1(day.worked)} <span className={of}>of {hours1(day.expected)}</span>
			<span className={cn("text-[11.5px] min-w-[3.2em] text-right", closed ? TONE[tone] : "")}>
				{closed
					? tone === "even"
						? "0.0"
						: `${delta > 0 ? "+" : "−"}${Math.abs(delta).toFixed(1)}`
					: ""}
			</span>
		</>
	);
}

export function WeekDays({
	project,
	todayIso,
	weekOf,
	onWeekChange,
	contractWeek,
	ledgerWeek,
	running,
	onChangeAbsence,
}: WeekDaysProps) {
	const thisMonday = mondayOfIso(todayIso);
	const isCurrent = weekOf === thisMonday;
	const { data: sessions, refetch } = useSessions(project.id);
	const { data: allProjects } = useProjects();
	const updateSession = useUpdateSession();
	const deleteSession = useDeleteSession();
	const { data: focusScores } = useFocusScores();
	const { byMondayIso: planned } = useProjectPlannedByWeek(project.id, [weekOf]);
	const { byMondayIso: commits } = useProjectGitActivityByWeek(project.id, [weekOf]);
	const now = useNow();

	const [open, setOpen] = useState<Record<string, boolean>>({});
	const [editing, setEditing] = useState<string | null>(null);
	const [confirming, setConfirming] = useState<string | null>(null);

	const isOpen = (date: string) => open[date] ?? date === todayIso;
	const toggle = (date: string) => setOpen((prev) => ({ ...prev, [date]: !isOpen(date) }));

	const days = buildDays(weekOf, todayIso, sessions ?? [], contractWeek, ledgerWeek, running, now);
	const focusByBeat = new Map((focusScores ?? []).map((f) => [f.beat_id, f.score]));

	const handleSave = async (
		sessionId: string,
		startTime: string,
		endTime: string,
		projectIdForSession: string,
	) => {
		const session = sessions?.find((s) => s.id === sessionId);
		if (!session) return;
		try {
			await updateSession.mutateAsync({
				session,
				startTime,
				endTime,
				projectId: projectIdForSession,
			});
			toast.success("Session updated");
			refetch();
			setEditing(null);
		} catch {
			toast.error("Failed to update session");
		}
	};

	const handleDelete = async (sessionId: string) => {
		try {
			await deleteSession.mutateAsync(sessionId);
			toast.success("Session deleted");
			refetch();
		} catch (err) {
			toast.error(describeError(err, "Failed to delete session"));
		}
		setConfirming(null);
	};

	const plannedHours = planned.get(weekOf);
	const commitCount = project.githubRepo ? commits.get(weekOf) : undefined;
	const foot: string[] = [];
	if (plannedHours !== undefined) foot.push(`Planned ${Math.round(plannedHours * 10) / 10} h`);
	if (commitCount !== undefined) foot.push(`${commitCount} commit${commitCount === 1 ? "" : "s"}`);
	if (running && isCurrent) foot.push(`Timer running since ${clock(running.since)}`);

	const noSessionsAtAll = (sessions?.length ?? 0) === 0 && !running;

	return (
		<Panel role="region" aria-label="Days" padding="px-6 py-[22px]">
			<div className="flex items-baseline gap-x-3 gap-y-2 flex-wrap">
				<h3 className={LABEL}>
					Days{" "}
					<span className={SUB}>
						{weekRange(weekOf)} · {weekNumber(weekOf)}
					</span>
				</h3>
				<div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
					{!isCurrent && (
						<button type="button" onClick={() => onWeekChange(thisMonday)} className={LINKISH}>
							Today
						</button>
					)}
					<span className="inline-flex items-center gap-1">
						<button
							type="button"
							onClick={() => onWeekChange(addIsoDays(weekOf, -7))}
							aria-label="Previous week"
							className={NAV_BUTTON}
						>
							<ChevronLeft className="w-3.5 h-3.5" aria-hidden="true" />
						</button>
						<button
							type="button"
							onClick={() => onWeekChange(addIsoDays(weekOf, 7))}
							aria-label="Next week"
							className={NAV_BUTTON}
						>
							<ChevronRight className="w-3.5 h-3.5" aria-hidden="true" />
						</button>
					</span>
				</div>
			</div>

			<div className="mt-3">
				{days.map((day) => {
					const expandable = day.sessions.length > 0 || day.live;
					const opened = expandable && isOpen(day.date);
					const closed = day.date < todayIso;
					const count = day.sessions.length;
					const mid = day.off ? (
						<>
							{/* Under 560 px the pill gives way with an ellipsis so "Change" stays in view. */}
							<span
								className={cn(
									TINT_PILL,
									TINT[day.off.kind],
									"@max-[560px]/content:block @max-[560px]/content:min-w-0 @max-[560px]/content:overflow-hidden @max-[560px]/content:text-ellipsis",
								)}
							>
								{day.off.label}
							</span>
							{day.off.changeable && (
								<button
									type="button"
									onClick={onChangeAbsence}
									className={cn(LINKISH, "relative z-10 shrink-0")}
								>
									Change
								</button>
							)}
						</>
					) : expandable ? (
						<span className="min-w-0 truncate">
							{count > 0 ? `${count} session${count === 1 ? "" : "s"}` : ""}
							{count > 0 && day.live ? " · " : ""}
							{day.live ? "running" : ""}
						</span>
					) : null;

					const name = (
						<span
							className={cn(
								"text-[13.5px] font-bold flex flex-wrap items-center gap-x-2 gap-y-1 whitespace-nowrap",
								day.isToday ? "text-accent-ink" : "text-foreground",
							)}
						>
							{day.name}{" "}
							<span className="text-muted-foreground font-mono font-bold">{day.number}</span>
							{day.isToday && " "}
							{day.isToday && (
								<span className="text-[10px] px-2 py-px rounded-full bg-accent text-accent-foreground tracking-[0.06em] whitespace-nowrap">
									today
								</span>
							)}
						</span>
					);
					const row = (
						<div
							data-day={day.date}
							className={cn(
								ROW,
								"relative",
								expandable && "hover:bg-secondary",
								day.isToday && "bg-accent/20",
							)}
						>
							{expandable ? (
								<button
									type="button"
									aria-expanded={opened}
									onClick={() => toggle(day.date)}
									className={TOGGLE}
								>
									{name}
								</button>
							) : (
								name
							)}
							<div className="text-[12.5px] text-muted-foreground font-medium flex gap-2 items-center min-w-0 flex-wrap @max-[560px]/content:flex-nowrap @max-[560px]/content:overflow-hidden @max-[560px]/content:whitespace-nowrap">
								{mid}
							</div>
							<div className="text-[13.5px] font-bold text-foreground whitespace-nowrap flex gap-2 items-center font-mono">
								<Figure day={day} closed={closed} />
								<span
									className={cn(
										"text-muted-foreground w-3.5 text-center transition-transform",
										opened && "rotate-90",
										!expandable && "invisible",
									)}
									aria-hidden="true"
								>
									›
								</span>
							</div>
						</div>
					);

					return (
						<div key={day.date} className="border-b border-border last:border-b-0">
							{row}
							{opened && (
								<div className="pl-[130px] @max-[560px]/content:pl-2 pr-1.5 pb-2.5 pt-0.5">
									{day.sessions.map((session) =>
										editing === session.id ? (
											<div key={session.id} className="py-1">
												<SessionEditForm
													session={session}
													projects={(allProjects ?? []).map((p) => ({ id: p.id, name: p.name }))}
													onSave={handleSave}
													onCancel={() => setEditing(null)}
												/>
											</div>
										) : (
											<div
												key={session.id}
												className="group grid grid-cols-[auto_minmax(0,1fr)_auto] gap-3 @max-[560px]/content:gap-2 items-center px-3 py-1.5 rounded-xl text-[13px] hover:bg-secondary"
											>
												<span className="text-[12.5px] font-bold font-mono text-foreground">
													{clock(session.startTime)} → {clock(session.endTime)}
												</span>
												<span className="text-muted-foreground font-medium truncate flex gap-1.5 items-center min-w-0">
													{session.note && <span className="truncate">{session.note}</span>}
													{session.tags.map((tag) => (
														<span
															key={tag}
															className="text-[10.5px] font-bold px-2 rounded-full bg-secondary text-tint-vacation-ink"
														>
															#{tag}
														</span>
													))}
													{day.isToday && focusByBeat.has(session.id) && (
														<span
															className="text-[10.5px] font-bold text-muted-foreground bg-tint-other rounded-full px-1.5"
															title="Focus score from the daemon"
														>
															◦ {Math.round(focusByBeat.get(session.id) ?? 0)}
														</span>
													)}
												</span>
												<span className="text-[12.5px] font-bold font-mono text-foreground flex items-center gap-2.5">
													{hoursMinutes(session.duration)}
													{confirming === session.id ? (
														<span className="inline-flex items-center gap-1">
															<Button
																type="button"
																variant="destructive"
																size="sm"
																className="h-6 px-2 text-[11px]"
																disabled={deleteSession.isPending}
																onClick={() => handleDelete(session.id)}
															>
																Delete
															</Button>
															<Button
																type="button"
																variant="ghost"
																size="sm"
																className="h-6 px-2 text-[11px]"
																onClick={() => setConfirming(null)}
															>
																Cancel
															</Button>
														</span>
													) : (
														// Hidden until hover only where there is hover: a phone shows them.
														<span className="inline-flex gap-0.5 [@media(hover:hover)]:opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity">
															<button
																type="button"
																onClick={() => setEditing(session.id)}
																aria-label="Edit session"
																className={OP}
															>
																<Pencil className="w-3 h-3" aria-hidden="true" />
															</button>
															<button
																type="button"
																onClick={() => setConfirming(session.id)}
																aria-label="Delete session"
																className={cn(OP, "hover:text-destructive")}
															>
																<Trash2 className="w-3 h-3" aria-hidden="true" />
															</button>
														</span>
													)}
												</span>
											</div>
										),
									)}
									{day.live && running && (
										<div className="grid grid-cols-[auto_minmax(0,1fr)_auto] gap-3 @max-[560px]/content:gap-2 items-center px-3 py-1.5 rounded-xl text-[13px]">
											<span className="text-[12.5px] font-bold font-mono text-foreground">
												{clock(running.since)} → now
											</span>
											<span className="text-muted-foreground font-medium truncate" />
											<span className="text-[12.5px] font-bold font-mono text-accent-ink flex items-center gap-2.5">
												<span className={LIVE_DOT} aria-hidden="true" />
												{hoursMinutes(
													Math.max(0, now - parseUtcIso(running.since).getTime()) / 60_000,
												)}
											</span>
										</div>
									)}
								</div>
							)}
						</div>
					);
				})}
			</div>

			{noSessionsAtAll && (
				<p className="mt-3 px-3 text-[13px] text-muted-foreground">
					No sessions yet — start the timer in the sidebar.
				</p>
			)}

			{foot.length > 0 && (
				<div className="text-[12.5px] px-3 pt-2.5 flex gap-4 flex-wrap font-medium text-muted-foreground">
					{foot.map((item) => (
						<span key={item}>{item}</span>
					))}
				</div>
			)}
		</Panel>
	);
}
