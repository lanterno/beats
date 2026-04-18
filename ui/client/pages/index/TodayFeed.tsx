/**
 * TodayFeed Component
 * Today's sessions listed compactly, with collapsible yesterday/earlier sections.
 */

import { ChevronDown, Clock } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useFocusScores } from "@/entities/intelligence";
import { useProjects } from "@/entities/project";
import type { Session } from "@/entities/session";
import { useGaps, useThisWeekSessions, useTodaySessions } from "@/entities/session";
import type { FocusScore, Gap } from "@/shared/api";
import { cn, formatDuration, formatTime, parseUtcIso, startOfDay } from "@/shared/lib";
import { EmptyState } from "@/shared/ui";

function focusColor(score: number): string {
	if (score >= 70) return "var(--color-accent)";
	if (score >= 40) return "var(--color-warning)";
	return "var(--color-destructive)";
}

function SessionRow({
	session,
	projectName,
	projectColor,
	projectId,
	focusScore,
}: {
	session: Session;
	projectName: string;
	projectColor: string;
	projectId: string;
	focusScore?: FocusScore;
}) {
	const navigate = useNavigate();

	return (
		<button
			onClick={() => navigate(`/project/${projectId}`)}
			className="w-full flex flex-col px-3 py-1.5 hover:bg-secondary/30 rounded-md transition-colors text-left"
		>
			<div className="flex items-center gap-2">
				<div
					className="w-1.5 h-1.5 rounded-full shrink-0"
					style={{ backgroundColor: projectColor }}
				/>
				<span className="text-sm text-foreground truncate flex-1 min-w-0">{projectName}</span>
				<span className="text-xs text-muted-foreground tabular-nums shrink-0">
					{formatTime(session.startTime)} → {formatTime(session.endTime)}
				</span>
				{focusScore && (
					<div
						className="w-1.5 h-1.5 rounded-full shrink-0"
						style={{ backgroundColor: focusColor(focusScore.score) }}
						title={`Focus: ${focusScore.score}`}
					/>
				)}
				<span className="text-sm font-medium tabular-nums text-foreground w-14 text-right shrink-0">
					{session.duration > 0 ? formatDuration(session.duration) : "—"}
				</span>
			</div>
			{(session.note || session.tags.length > 0) && (
				<div className="flex items-center gap-1.5 ml-4 mt-0.5">
					{session.note && (
						<span className="text-[11px] text-muted-foreground/70 truncate">{session.note}</span>
					)}
					{session.tags.map((tag) => (
						<span
							key={tag}
							className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent/10 text-accent/70"
						>
							{tag}
						</span>
					))}
				</div>
			)}
		</button>
	);
}

function GapRow({ gap }: { gap: Gap }) {
	return (
		<div className="flex items-center gap-2 px-3 py-1 opacity-60">
			<div className="w-1.5 h-1.5 rounded-full shrink-0 border border-dashed border-muted-foreground/40" />
			<span className="text-xs text-muted-foreground italic flex-1">Untracked</span>
			<span className="text-xs text-muted-foreground tabular-nums shrink-0">
				{formatTime(gap.start)} → {formatTime(gap.end)}
			</span>
			<span className="text-xs tabular-nums text-muted-foreground w-14 text-right shrink-0">
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
}: {
	label: string;
	sessions: Session[];
	totalMinutes: number;
	projectMap: Map<string, { name: string; color: string }>;
	defaultOpen: boolean;
	focusScoreMap?: Map<string, FocusScore>;
}) {
	const [open, setOpen] = useState(defaultOpen);

	if (sessions.length === 0) return null;

	return (
		<div>
			<button
				onClick={() => setOpen(!open)}
				className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-secondary/20 rounded-md transition-colors"
			>
				<ChevronDown
					className={cn(
						"w-3 h-3 text-muted-foreground transition-transform duration-150",
						!open && "-rotate-90",
					)}
				/>
				<span className="text-xs uppercase tracking-[0.1em] text-muted-foreground font-medium">
					{label}
				</span>
				<span className="text-xs text-muted-foreground/60">
					— {sessions.length} session{sessions.length !== 1 ? "s" : ""}
				</span>
				<span className="ml-auto text-xs font-medium tabular-nums text-muted-foreground">
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
								projectColor={info?.color || "#888"}
								projectId={session.projectId}
								focusScore={focusScoreMap?.get(session.id)}
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

	const projectMap = new Map((projects || []).map((p) => [p.id, { name: p.name, color: p.color }]));
	const focusScoreMap = new Map((focusScores ?? []).map((f) => [f.beat_id, f]));

	const today = startOfDay();

	const yesterday = new Date(today);
	yesterday.setDate(yesterday.getDate() - 1);

	// Split week sessions into yesterday and earlier (excluding today)
	const yesterdaySessions = (weekSessions || []).filter((s) => {
		const d = parseUtcIso(s.startTime);
		return d >= yesterday && d < today;
	});

	const earlierSessions = (weekSessions || []).filter((s) => {
		const d = parseUtcIso(s.startTime);
		return d < yesterday;
	});

	const todayTotal = (todaySessions || []).reduce((sum, s) => sum + s.duration, 0);
	const avgFocus =
		focusScores && focusScores.length > 0
			? Math.round(focusScores.reduce((sum, f) => sum + f.score, 0) / focusScores.length)
			: null;
	const yesterdayTotal = yesterdaySessions.reduce((sum, s) => sum + s.duration, 0);
	const earlierTotal = earlierSessions.reduce((sum, s) => sum + s.duration, 0);

	const todayList = todaySessions || [];

	return (
		<div>
			<h2 className="flex items-center gap-2 text-foreground font-medium text-sm mb-3">
				<Clock className="w-3.5 h-3.5 text-accent/75" />
				Activity
			</h2>

			<div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden">
				{/* Today section — always open */}
				<div className="px-1 py-2">
					<div className="flex items-center gap-2 px-3 py-1 mb-0.5">
						<span className="text-xs uppercase tracking-[0.1em] text-accent font-semibold">
							Today
						</span>
						{todayList.length > 0 && (
							<span className="text-xs text-muted-foreground/60">
								— {todayList.length} session{todayList.length !== 1 ? "s" : ""}
							</span>
						)}
						{avgFocus !== null && (
							<span className="text-xs text-muted-foreground/60">Focus: {avgFocus}</span>
						)}
						<span className="ml-auto text-sm font-medium tabular-nums text-accent">
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
									projectColor={info?.color || "#888"}
									projectId={session.projectId}
									focusScore={focusScoreMap.get(session.id)}
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
					<div className="border-t border-border/40 px-1 py-1.5">
						<SessionGroup
							label="Yesterday"
							sessions={yesterdaySessions}
							totalMinutes={yesterdayTotal}
							projectMap={projectMap}
							defaultOpen={false}
						/>
						<SessionGroup
							label="Earlier this week"
							sessions={earlierSessions}
							totalMinutes={earlierTotal}
							projectMap={projectMap}
							defaultOpen={false}
						/>
					</div>
				)}
			</div>
		</div>
	);
}
