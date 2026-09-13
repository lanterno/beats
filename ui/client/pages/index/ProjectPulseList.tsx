/**
 * ProjectPulseList Component
 * Compact project rows showing sparkline, today's hours, and goal progress.
 * Designed to show data NOT already in the sidebar (which shows name + weekly hours).
 */

import { Layers, Plus, Star } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import {
	BalanceChip,
	NewProjectDialog,
	sortProjectsForList,
	usePinnedProjects,
	useProjects,
	visibleProjects,
	weekGoalView,
} from "@/entities/project";
import { useAllBeats } from "@/entities/session";
import type { ApiBeat } from "@/shared/api";
import { cn, getCurrentWeekRange, getDayName, parseUtcIso, startOfDay } from "@/shared/lib";
import { Button, EmptyState, GoalRing, Panel } from "@/shared/ui";

/** A section heading on the sky: the mockup's `.lbl`, in ink so it reads there. */
const SKY_HEADING =
	"flex items-center gap-2 px-2 mb-2.5 font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-foreground";

interface DaySummary {
	day: string;
	hours: number;
	date: Date;
	totalMinutes: number;
}

function MiniSparkline({ data, className }: { data: DaySummary[]; className?: string }) {
	const maxMinutes = Math.max(...data.map((d) => d.totalMinutes), 1);

	return (
		<div className={cn("flex items-end gap-px h-3 shrink-0", className)}>
			{data.map((day, i) => {
				const h = day.totalMinutes > 0 ? Math.max((day.totalMinutes / maxMinutes) * 12, 1.5) : 0;
				const isToday = day.date.toDateString() === new Date().toDateString();
				return (
					<div
						key={i}
						className={cn(
							"w-1.5 rounded-t-sm origin-bottom",
							isToday
								? "bg-accent"
								: day.totalMinutes > 0
									? "bg-muted-foreground/35"
									: "bg-muted-foreground/10",
						)}
						style={{
							height: `${h}px`,
							animation: `sparkGrow 300ms ease-out ${i * 40}ms both`,
						}}
					/>
				);
			})}
		</div>
	);
}

function buildSummaries(beats: ApiBeat[]): Record<string, DaySummary[]> {
	const { start, end } = getCurrentWeekRange();
	const weeklyBeats = beats.filter((beat) => {
		if (!beat.start || !beat.end) return false;
		const startTime = parseUtcIso(beat.start);
		return startTime >= start && startTime <= end;
	});

	// Group by project
	const byProject = new Map<string, Map<string, number>>();
	for (const beat of weeklyBeats) {
		if (!beat.start || !beat.end || !beat.project_id) continue;
		const duration = (new Date(beat.end).getTime() - new Date(beat.start).getTime()) / 1000 / 60;
		const dayKey = parseUtcIso(beat.start).toDateString();
		if (!byProject.has(beat.project_id)) byProject.set(beat.project_id, new Map());
		const dailyTotals = byProject.get(beat.project_id)!;
		dailyTotals.set(dayKey, (dailyTotals.get(dayKey) || 0) + duration);
	}

	const { start: weekStart } = getCurrentWeekRange();
	const result: Record<string, DaySummary[]> = {};
	for (const [projectId, dailyTotals] of byProject) {
		result[projectId] = Array.from({ length: 7 }, (_, i) => {
			const dayDate = new Date(weekStart);
			dayDate.setDate(weekStart.getDate() + i);
			dayDate.setHours(0, 0, 0, 0);
			const minutes = dailyTotals.get(dayDate.toDateString()) || 0;
			return {
				day: getDayName(dayDate),
				hours: minutes / 60,
				date: dayDate,
				totalMinutes: minutes,
			};
		});
	}
	return result;
}

export function ProjectPulseList() {
	const navigate = useNavigate();
	const { data: projects } = useProjects();
	const { data: allBeats } = useAllBeats();
	const [dialogOpen, setDialogOpen] = useState(false);

	const summaries = useMemo(() => (allBeats ? buildSummaries(allBeats) : undefined), [allBeats]);

	const { pins, toggle: togglePinId, isPinned } = usePinnedProjects();
	const sorted = sortProjectsForList(visibleProjects(projects), { pinnedIds: pins });

	const today = startOfDay();

	if (sorted.length === 0) {
		return (
			<div>
				<h2 className={SKY_HEADING}>
					<Layers className="w-3.5 h-3.5 text-muted-foreground" />
					Projects
				</h2>
				<Panel padding="p-0" className="flex flex-col items-center">
					<EmptyState variant="seedling" message="No projects yet. Create one to start tracking." />
					<Button type="button" size="sm" className="mb-5" onClick={() => setDialogOpen(true)}>
						<Plus className="w-3.5 h-3.5" />
						New project
					</Button>
				</Panel>
				<NewProjectDialog
					open={dialogOpen}
					onClose={() => setDialogOpen(false)}
					onCreated={(project) => navigate(`/project/${project.id}`)}
				/>
			</div>
		);
	}

	return (
		<div>
			<h2 className={SKY_HEADING}>
				<Layers className="w-3.5 h-3.5 text-muted-foreground" />
				Projects
			</h2>

			<Panel padding="px-4 py-2.5">
				<div className="flex flex-col">
					{sorted.map((project) => {
						const summary = summaries?.[project.id];
						const todayMinutes =
							summary?.find((d) => d.date.toDateString() === today.toDateString())?.totalMinutes ??
							0;
						const todayHours = todayMinutes / 60;
						const isInactive = project.weeklyMinutes === 0;
						// The contract's expected and worked on a day job it governs, with
						// the running balance; the personal goal's figures on everything else.
						const week = weekGoalView(project);
						const goalPct = week.goal ? Math.min((week.hours / week.goal) * 100, 100) : null;

						const pinned = isPinned(project.id);
						return (
							<div key={project.id} className="border-t border-border first:border-t-0">
								<div
									className={cn(
										"group w-full flex items-center gap-2.5 px-2 py-2 -mx-1.5 my-0.5 rounded-xl hover:bg-secondary transition-colors",
									)}
								>
									<button
										type="button"
										onClick={() => navigate(`/project/${project.id}`)}
										className="flex items-center gap-2.5 flex-1 min-w-0 text-left rounded-lg focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
									>
										{/* A quiet week dims the marks and greys the name, never the row: the
										    balance chip of a day job owing hours must not fade with it. */}
										<div
											className={cn("w-2 h-2 rounded-full shrink-0", isInactive && "opacity-45")}
											style={{ backgroundColor: project.color }}
										/>
										<span
											className={cn(
												"text-[13.5px] font-bold truncate min-w-0 flex-1",
												isInactive ? "text-muted-foreground" : "text-foreground",
											)}
										>
											{project.name}
										</span>

										{summary && (
											<MiniSparkline data={summary} className={cn(isInactive && "opacity-45")} />
										)}

										<span
											className={cn(
												"text-xs font-mono font-bold shrink-0 w-10 text-right",
												todayHours > 0 ? "text-foreground" : "text-muted-foreground font-medium",
											)}
										>
											{todayHours > 0 ? `${todayHours.toFixed(1)}h` : "—"}
										</span>

										{goalPct !== null && (
											<GoalRing
												percent={goalPct}
												size={22}
												strokeWidth={2.5}
												isCap={week.goalType === "cap"}
											/>
										)}
										{week.balance !== null && <BalanceChip hours={week.balance} />}
									</button>
									<button
										type="button"
										onClick={() => togglePinId(project.id)}
										aria-label={pinned ? `Unpin ${project.name}` : `Pin ${project.name}`}
										aria-pressed={pinned}
										title={pinned ? "Unpin from top" : "Pin to top"}
										className={cn(
											"p-1 rounded-full transition-all shrink-0 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
											pinned
												? "text-accent-ink"
												: "text-muted-foreground/50 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 hover:text-accent-ink",
										)}
									>
										<Star
											className="w-3 h-3"
											fill={pinned ? "currentColor" : "none"}
											aria-hidden="true"
										/>
									</button>
								</div>
							</div>
						);
					})}
				</div>
			</Panel>
		</div>
	);
}
