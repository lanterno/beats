/**
 * TodayFeed Component
 * Today's sessions listed compactly, with collapsible yesterday/earlier sections.
 */

import { ChevronDown, Clock, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { useFocusScores } from "@/entities/intelligence";
import { ProjectPicker, useProjects, visibleProjects } from "@/entities/project";
import type { Session } from "@/entities/session";
import {
	useDeleteSession,
	useGaps,
	useThisWeekSessions,
	useTodaySessions,
} from "@/entities/session";
import { describeError, type FocusScore, type Gap } from "@/shared/api";
import { cn, formatDuration, formatTime, parseUtcIso, startOfDay } from "@/shared/lib";
import { Button, EmptyState, Panel } from "@/shared/ui";

const LABEL = "font-body text-[10.5px] font-bold uppercase tracking-[0.14em]";

/** Edit-style round control, as on the project page's session rows. */
const OP =
	"grid place-items-center w-6 h-6 rounded-full text-muted-foreground hover:bg-sidebar-accent hover:text-foreground transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

// Leaf for a focused session, persimmon for a scattered one, the muted ink
// between. There is no warning token: the middle band used to name one and
// drew no dot at all.
function focusColor(score: number): string {
	if (score >= 70) return "var(--color-success)";
	if (score >= 40) return "var(--color-muted-foreground)";
	return "var(--color-destructive)";
}

/** A session whose project has no colour. */
const NO_COLOR = "var(--color-muted-foreground)";

function SessionRow({
	session,
	projectName,
	projectColor,
	projectId,
	projectArchived,
	focusScore,
	onDelete,
	deleting,
}: {
	session: Session;
	projectName: string;
	projectColor: string;
	projectId: string;
	projectArchived?: boolean;
	focusScore?: FocusScore;
	onDelete?: (sessionId: string) => void;
	deleting?: boolean;
}) {
	const navigate = useNavigate();
	const [confirming, setConfirming] = useState(false);

	return (
		<div className="group w-full flex flex-col px-3 py-1.5 hover:bg-secondary rounded-xl transition-colors">
			<div className="flex items-center gap-2">
				<button
					type="button"
					onClick={() => navigate(`/project/${projectId}`)}
					className="flex items-center gap-2 flex-1 min-w-0 text-left rounded-lg focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
				>
					<div
						className="w-2 h-2 rounded-full shrink-0"
						style={{ backgroundColor: projectColor }}
					/>
					<span className="text-[13px] font-bold text-foreground truncate flex-1 min-w-0">
						{projectName}
					</span>
					{projectArchived && (
						<span
							className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-px rounded-full bg-secondary text-muted-foreground shrink-0"
							title="This project is archived"
						>
							Archived
						</span>
					)}
					<span className="text-xs font-mono font-bold text-muted-foreground shrink-0">
						{formatTime(session.startTime)} → {formatTime(session.endTime)}
					</span>
					{focusScore && (
						<div
							className="w-1.5 h-1.5 rounded-full shrink-0"
							style={{ backgroundColor: focusColor(focusScore.score) }}
							title={`Focus: ${focusScore.score}`}
						/>
					)}
					<span className="text-[12.5px] font-mono font-bold text-foreground min-w-14 whitespace-nowrap text-right shrink-0">
						{session.duration > 0 ? formatDuration(session.duration) : "—"}
					</span>
				</button>
				{onDelete &&
					(confirming ? (
						<div className="flex items-center gap-1 shrink-0">
							<Button
								type="button"
								variant="destructive"
								size="sm"
								className="h-6 px-2 text-[11px]"
								onClick={() => onDelete(session.id)}
								disabled={deleting}
							>
								Delete
							</Button>
							<Button
								type="button"
								variant="ghost"
								size="sm"
								className="h-6 px-2 text-[11px]"
								onClick={() => setConfirming(false)}
							>
								Cancel
							</Button>
						</div>
					) : (
						<button
							type="button"
							onClick={() => setConfirming(true)}
							aria-label="Delete session"
							// Hidden until hover only where there is hover: a phone shows it.
							className={`${OP} shrink-0 [@media(hover:hover)]:opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity`}
						>
							<Trash2 className="w-3.5 h-3.5" />
						</button>
					))}
			</div>
			{(session.note || session.tags.length > 0) && (
				<div className="flex items-center gap-1.5 ml-4 mt-0.5">
					{session.note && (
						<span className="text-[11.5px] font-medium text-muted-foreground truncate">
							{session.note}
						</span>
					)}
					{session.tags.map((tag) => (
						<span
							key={tag}
							className="text-[10.5px] font-bold px-2 rounded-full bg-secondary text-tint-vacation-ink"
						>
							{tag}
						</span>
					))}
				</div>
			)}
		</div>
	);
}

function GapRow({ gap }: { gap: Gap }) {
	return (
		<div className="flex items-center gap-2 px-3 py-1">
			<div className="w-2 h-2 rounded-full shrink-0 bg-muted" />
			<span className="text-xs font-medium text-muted-foreground italic flex-1">Untracked</span>
			<span className="text-xs font-mono font-bold text-muted-foreground shrink-0">
				{formatTime(gap.start)} → {formatTime(gap.end)}
			</span>
			<span className="text-xs font-mono font-bold text-muted-foreground min-w-14 whitespace-nowrap text-right shrink-0">
				{formatDuration(gap.duration_minutes)}
			</span>
		</div>
	);
}

/**
 * Merge today's sessions and gaps into a single timeline sorted by start time.
 */
function buildTimeline(
	sessions: Session[],
	gaps: Gap[],
): Array<{ type: "session" | "gap"; data: Session | Gap }> {
	const items: Array<{ type: "session" | "gap"; data: Session | Gap; time: number }> = [];
	for (const s of sessions) {
		items.push({ type: "session", data: s, time: new Date(s.startTime).getTime() });
	}
	for (const g of gaps) {
		items.push({ type: "gap", data: g, time: new Date(g.start).getTime() });
	}
	items.sort((a, b) => a.time - b.time);
	return items.map(({ type, data }) => ({ type, data }));
}

function SessionGroup({
	label,
	sessions,
	totalMinutes,
	projectMap,
	defaultOpen,
	focusScoreMap,
	onDelete,
	deleting,
}: {
	label: string;
	sessions: Session[];
	totalMinutes: number;
	projectMap: Map<string, { name: string; color: string; archived: boolean }>;
	defaultOpen: boolean;
	focusScoreMap?: Map<string, FocusScore>;
	onDelete?: (sessionId: string) => void;
	deleting?: boolean;
}) {
	const [open, setOpen] = useState(defaultOpen);

	if (sessions.length === 0) return null;

	return (
		<div>
			<button
				type="button"
				onClick={() => setOpen(!open)}
				className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-secondary rounded-xl transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
			>
				<ChevronDown
					className={cn(
						"w-3 h-3 text-muted-foreground transition-transform duration-150",
						!open && "-rotate-90",
					)}
				/>
				<span className={`${LABEL} text-muted-foreground`}>{label}</span>
				<span className="text-xs font-medium text-muted-foreground">
					— {sessions.length} session{sessions.length !== 1 ? "s" : ""}
				</span>
				<span className="ml-auto text-xs font-mono font-bold text-muted-foreground">
					{formatDuration(totalMinutes)}
				</span>
			</button>
			{open && (
				<div className="mt-0.5">
					{sessions.map((session) => {
						const info = projectMap.get(session.projectId);
						return (
							<SessionRow
								key={session.id}
								session={session}
								projectName={info?.name || "Unknown"}
								projectColor={info?.color || NO_COLOR}
								projectId={session.projectId}
								projectArchived={info?.archived}
								focusScore={focusScoreMap?.get(session.id)}
								onDelete={onDelete}
								deleting={deleting}
							/>
						);
					})}
				</div>
			)}
		</div>
	);
}

export function TodayFeed() {
	const { data: todaySessions } = useTodaySessions();
	const { data: weekSessions } = useThisWeekSessions();
	const { data: projects } = useProjects();
	const { data: focusScores } = useFocusScores();
	const { data: gaps } = useGaps();
	const deleteSession = useDeleteSession();

	const handleDelete = (sessionId: string) => {
		deleteSession.mutate(sessionId, {
			onSuccess: () => toast.success("Session deleted"),
			onError: (err) => toast.error(describeError(err, "Failed to delete session")),
		});
	};

	// Map includes archived projects so a session whose project got archived
	// keeps rendering its name (with an "Archived" chip via SessionRow) instead
	// of falling through to "Unknown".
	const projectMap = new Map(
		(projects || []).map((p) => [p.id, { name: p.name, color: p.color, archived: p.archived }]),
	);
	const focusScoreMap = new Map((focusScores ?? []).map((f) => [f.beat_id, f]));

	// Per-project scope toggle (P2.4) — useful when a user wants to see only
	// one project's day at a glance. Default null = all projects.
	const [filterProjectId, setFilterProjectId] = useState<string | null>(null);
	const pickerProjects = useMemo(() => visibleProjects(projects), [projects]);

	const scopeToFilter = <T extends { projectId: string }>(list: T[]): T[] =>
		filterProjectId ? list.filter((s) => s.projectId === filterProjectId) : list;

	const today = startOfDay();

	const yesterday = new Date(today);
	yesterday.setDate(yesterday.getDate() - 1);

	// Split week sessions into yesterday and earlier (excluding today)
	const yesterdaySessions = scopeToFilter(
		(weekSessions || []).filter((s) => {
			const d = parseUtcIso(s.startTime);
			return d >= yesterday && d < today;
		}),
	);

	const earlierSessions = scopeToFilter(
		(weekSessions || []).filter((s) => {
			const d = parseUtcIso(s.startTime);
			return d < yesterday;
		}),
	);

	const filteredTodaySessions = scopeToFilter(todaySessions || []);
	const todayTotal = filteredTodaySessions.reduce((sum, s) => sum + s.duration, 0);
	const avgFocus =
		focusScores && focusScores.length > 0
			? Math.round(focusScores.reduce((sum, f) => sum + f.score, 0) / focusScores.length)
			: null;
	const yesterdayTotal = yesterdaySessions.reduce((sum, s) => sum + s.duration, 0);
	const earlierTotal = earlierSessions.reduce((sum, s) => sum + s.duration, 0);

	const todayList = filteredTodaySessions;

	return (
		<div>
			<div className="flex items-center gap-2 mb-3">
				<h2 className={`flex items-center gap-2 px-2 ${LABEL} text-foreground`}>
					<Clock className="w-3.5 h-3.5 text-muted-foreground" />
					Activity
				</h2>
				<div className="ml-auto flex items-center gap-1 w-44">
					<ProjectPicker
						projects={pickerProjects}
						value={filterProjectId}
						onChange={setFilterProjectId}
						compact
						triggerPlaceholder="All projects"
						ariaLabel="Filter activity by project"
					/>
					{filterProjectId && (
						<button
							type="button"
							onClick={() => setFilterProjectId(null)}
							aria-label="Clear project filter"
							title="Show all projects"
							className="grid place-items-center w-7 h-7 shrink-0 rounded-full bg-sidebar text-foreground hover:bg-card transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
						>
							<X className="w-3.5 h-3.5" />
						</button>
					)}
				</div>
			</div>

			<Panel padding="px-3 py-3">
				{/* Today section — always open */}
				<div className="pb-1">
					<div className="flex items-center gap-2 px-3 py-1 mb-0.5">
						<span className={`${LABEL} text-accent-ink`}>Today</span>
						{todayList.length > 0 && (
							<span className="text-xs font-medium text-muted-foreground">
								— {todayList.length} session{todayList.length !== 1 ? "s" : ""}
							</span>
						)}
						{avgFocus !== null && (
							<span className="text-xs font-medium text-muted-foreground">Focus: {avgFocus}</span>
						)}
						<span className="ml-auto text-sm font-mono font-extrabold text-foreground">
							{todayTotal > 0 ? formatDuration(todayTotal) : "0m"}
						</span>
					</div>

					{todayList.length > 0 ? (
						buildTimeline(todayList, gaps ?? []).map((item) => {
							if (item.type === "gap") {
								const gap = item.data as Gap;
								return <GapRow key={`gap-${gap.start}`} gap={gap} />;
							}
							const session = item.data as Session;
							const info = projectMap.get(session.projectId);
							return (
								<SessionRow
									key={session.id}
									session={session}
									projectName={info?.name || "Unknown"}
									projectColor={info?.color || NO_COLOR}
									projectId={session.projectId}
									projectArchived={info?.archived}
									focusScore={focusScoreMap.get(session.id)}
									onDelete={handleDelete}
									deleting={deleteSession.isPending}
								/>
							);
						})
					) : (
						<div className="px-3 py-2">
							<EmptyState
								variant="clock"
								message="No sessions yet. Start the timer to begin tracking."
							/>
						</div>
					)}
				</div>

				{/* Yesterday + Earlier — collapsible */}
				{(yesterdaySessions.length > 0 || earlierSessions.length > 0) && (
					<div className="border-t border-border pt-1.5">
						<SessionGroup
							label="Yesterday"
							sessions={yesterdaySessions}
							totalMinutes={yesterdayTotal}
							projectMap={projectMap}
							defaultOpen={false}
							onDelete={handleDelete}
							deleting={deleteSession.isPending}
						/>
						<SessionGroup
							label="Earlier this week"
							sessions={earlierSessions}
							totalMinutes={earlierTotal}
							projectMap={projectMap}
							defaultOpen={false}
							onDelete={handleDelete}
							deleting={deleteSession.isPending}
						/>
					</div>
				)}
			</Panel>
		</div>
	);
}
