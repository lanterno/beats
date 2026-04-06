/**
 * ProjectPulseList Component
 * Compact project rows showing sparkline, today's hours, and goal progress.
 * Designed to show data NOT already in the sidebar (which shows name + weekly hours).
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Layers } from "lucide-react";
import { cn, parseUtcIso, getCurrentWeekRange, getDayName } from "@/shared/lib";
import { useProjects } from "@/entities/project";
import { fetchBeats } from "@/entities/session";
import type { ApiBeat } from "@/shared/api";

interface DaySummary {
  day: string;
  hours: number;
  date: Date;
  totalMinutes: number;
}

function MiniSparkline({ data }: { data: DaySummary[] }) {
  const maxMinutes = Math.max(...data.map((d) => d.totalMinutes), 1);

  return (
    <div className="flex items-end gap-px h-3 shrink-0">
      {data.map((day, i) => {
        const h = day.totalMinutes > 0 ? Math.max((day.totalMinutes / maxMinutes) * 12, 1.5) : 0;
        const isToday = day.date.toDateString() === new Date().toDateString();
        return (
          <div
            key={i}
            className={cn(
              "w-1.5 rounded-t-sm",
              isToday ? "bg-accent" : day.totalMinutes > 0 ? "bg-muted-foreground/35" : "bg-muted-foreground/10"
            )}
            style={{ height: `${h}px` }}
          />
        );
      })}
    </div>
  );
}

export function ProjectPulseList() {
  const navigate = useNavigate();
  const { data: projects } = useProjects();
  const [summaries, setSummaries] = useState<Record<string, DaySummary[]>>({});

  const fetchSummary = useCallback(async (projectId: string) => {
    try {
      const { start, end } = getCurrentWeekRange();
      const beats = await fetchBeats(projectId);
      const weeklyBeats = beats.filter((beat: ApiBeat) => {
        if (!beat.start || !beat.end) return false;
        const startTime = parseUtcIso(beat.start);
        return startTime >= start && startTime <= end;
      });

      const dailyTotals = new Map<string, number>();
      weeklyBeats.forEach((beat: ApiBeat) => {
        if (!beat.start || !beat.end) return;
        const duration =
          (new Date(beat.end).getTime() - new Date(beat.start).getTime()) / 1000 / 60;
        const dayKey = parseUtcIso(beat.start).toDateString();
        dailyTotals.set(dayKey, (dailyTotals.get(dayKey) || 0) + duration);
      });

      const { start: weekStart } = getCurrentWeekRange();
      const summary: DaySummary[] = Array.from({ length: 7 }, (_, i) => {
        const dayDate = new Date(weekStart);
        dayDate.setDate(weekStart.getDate() + i);
        dayDate.setHours(0, 0, 0, 0);
        const dayKey = dayDate.toDateString();
        const minutes = dailyTotals.get(dayKey) || 0;
        return {
          day: getDayName(dayDate),
          hours: minutes / 60,
          date: dayDate,
          totalMinutes: minutes,
        };
      });

      setSummaries((prev) => ({ ...prev, [projectId]: summary }));
    } catch {
      // silently fail
    }
  }, []);

  const projectsList = projects || [];

  useEffect(() => {
    for (const p of projectsList) {
      if (p.weeklyMinutes > 0 && !summaries[p.id]) {
        fetchSummary(p.id);
      }
    }
  }, [projectsList, summaries, fetchSummary]);

  const active = projectsList
    .filter((p) => p.weeklyMinutes > 0)
    .sort((a, b) => b.weeklyMinutes - a.weeklyMinutes);
  const inactive = projectsList
    .filter((p) => p.weeklyMinutes === 0)
    .sort((a, b) => a.name.localeCompare(b.name));
  const sorted = [...active, ...inactive];

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  if (sorted.length === 0) {
    return (
      <div>
        <h2 className="flex items-center gap-2 text-foreground font-medium text-sm mb-3">
          <Layers className="w-3.5 h-3.5 text-accent/75" />
          Projects
        </h2>
        <div className="rounded-lg border border-dashed border-border py-8 text-center">
          <p className="text-muted-foreground text-xs">No projects yet.</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h2 className="flex items-center gap-2 text-foreground font-medium text-sm mb-3">
        <Layers className="w-3.5 h-3.5 text-accent/75" />
        Projects
      </h2>

      <div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden">
        <div className="py-1">
          {sorted.map((project) => {
            const summary = summaries[project.id];
            const todayMinutes = summary?.find(
              (d) => d.date.toDateString() === today.toDateString()
            )?.totalMinutes ?? 0;
            const todayHours = todayMinutes / 60;
            const isInactive = project.weeklyMinutes === 0;
            const goalPct = project.weeklyGoal
              ? Math.min((project.weeklyMinutes / 60 / project.weeklyGoal) * 100, 100)
              : null;

            return (
              <button
                key={project.id}
                onClick={() => navigate(`/project/${project.id}`)}
                className={cn(
                  "w-full flex items-center gap-2.5 px-3 py-2 hover:bg-secondary/40 transition-colors text-left",
                  isInactive && "opacity-45"
                )}
              >
                <div
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ backgroundColor: project.color }}
                />
                <span className="text-sm font-medium text-foreground truncate min-w-0 flex-1">
                  {project.name}
                </span>

                {summary && <MiniSparkline data={summary} />}

                <span
                  className={cn(
                    "text-xs tabular-nums shrink-0 w-10 text-right",
                    todayHours > 0 ? "text-foreground" : "text-muted-foreground/40"
                  )}
                >
                  {todayHours > 0 ? `${todayHours.toFixed(1)}h` : "—"}
                </span>

                {goalPct !== null && (
                  <div className="w-14 h-1.5 rounded-full bg-muted shrink-0">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all",
                        goalPct >= 100 ? "bg-success" : "bg-accent/80"
                      )}
                      style={{ width: `${goalPct}%` }}
                    />
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
