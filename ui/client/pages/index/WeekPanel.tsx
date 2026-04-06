/**
 * WeekPanel Component
 * Navigable week section with two views:
 * - Daily view: per-project colored blocks per day
 * - Project totals view: horizontal bars showing weekly total per project
 */
import { useState } from "react";
import { ChevronLeft, ChevronRight, CalendarDays, List } from "lucide-react";
import { cn, getWeekRange, formatDateShort, formatDuration } from "@/shared/lib";
import { useProjects } from "@/entities/project";
import { useWeeklySessionsByProject } from "@/entities/session";
import type { DayProjectBreakdown } from "@/entities/session";

type ViewMode = "daily" | "projects";

export function WeekPanel() {
  const [weekOffset, setWeekOffset] = useState(0);
  const [view, setView] = useState<ViewMode>("daily");

  const { data: projects } = useProjects();
  const { data: weekData, isLoading } = useWeeklySessionsByProject(projects, weekOffset);

  const { start, end } = getWeekRange(weekOffset);
  const weekTotal = weekData?.reduce((sum, d) => sum + d.totalMinutes, 0) ?? 0;

  const weekLabel =
    weekOffset === 0
      ? "This Week"
      : weekOffset === -1
        ? "Last Week"
        : `${formatDateShort(start)} — ${formatDateShort(end)}`;

  return (
    <div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden">
      {/* Navigation row */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border/40">
        <button
          onClick={() => setWeekOffset((w) => w - 1)}
          className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary/50 transition-colors"
          aria-label="Previous week"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>

        <div className="text-center min-w-[140px]">
          <span className="text-sm font-medium text-foreground">{weekLabel}</span>
          {weekOffset !== 0 && (
            <span className="text-xs text-muted-foreground ml-1.5 hidden sm:inline">
              {formatDateShort(start)} — {formatDateShort(end)}
            </span>
          )}
          {weekOffset === 0 && (
            <span className="text-xs text-muted-foreground ml-1.5 hidden sm:inline">
              {formatDateShort(start)} — {formatDateShort(end)}
            </span>
          )}
        </div>

        <button
          onClick={() => setWeekOffset((w) => Math.min(w + 1, 0))}
          disabled={weekOffset >= 0}
          className={cn(
            "p-1 rounded-md transition-colors",
            weekOffset >= 0
              ? "text-muted-foreground/30 cursor-not-allowed"
              : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
          )}
          aria-label="Next week"
        >
          <ChevronRight className="w-4 h-4" />
        </button>

        {weekOffset !== 0 && (
          <button
            onClick={() => setWeekOffset(0)}
            className="px-2 py-0.5 rounded-md text-xs text-accent hover:bg-accent/10 transition-colors"
          >
            Today
          </button>
        )}

        <div className="ml-auto flex items-center gap-2">
          {weekTotal > 0 && (
            <span className="text-sm font-medium tabular-nums text-accent">
              {formatDuration(weekTotal)}
            </span>
          )}

          <div className="flex rounded-md border border-border overflow-hidden">
            <button
              onClick={() => setView("daily")}
              className={cn(
                "p-1.5 transition-colors",
                view === "daily"
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
              )}
              aria-label="Daily breakdown"
              title="Daily breakdown"
            >
              <CalendarDays className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setView("projects")}
              className={cn(
                "p-1.5 transition-colors border-l border-border",
                view === "projects"
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
              )}
              aria-label="Project totals"
              title="Project totals"
            >
              <List className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="h-32 flex items-center justify-center text-muted-foreground text-xs">
          Loading...
        </div>
      ) : weekData && view === "daily" ? (
        <DailyView data={weekData} />
      ) : weekData && view === "projects" ? (
        <ProjectTotalsView data={weekData} />
      ) : (
        <div className="h-32 flex items-center justify-center text-muted-foreground/40 text-xs">
          No data
        </div>
      )}
    </div>
  );
}

function DailyView({ data }: { data: DayProjectBreakdown[] }) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  return (
    <div className="grid grid-cols-7 gap-px bg-border/30">
      {data.map((day) => {
        const isToday = day.date.getTime() === today.getTime();

        return (
          <div
            key={day.dayName}
            className={cn(
              "bg-card px-1.5 py-1.5 min-h-[100px] flex flex-col",
              isToday && "bg-accent/[0.03]"
            )}
          >
            {/* Day header */}
            <div className="text-center mb-1">
              <p
                className={cn(
                  "text-[10px] uppercase tracking-wide leading-none",
                  isToday ? "text-accent font-semibold" : "text-muted-foreground"
                )}
              >
                {day.dayName}
              </p>
              <p
                className={cn(
                  "text-[10px] mt-0.5 leading-none",
                  isToday ? "text-accent/70" : "text-muted-foreground/50"
                )}
              >
                {formatDateShort(day.date)}
              </p>
            </div>

            {/* Project segments */}
            {day.segments.length > 0 ? (
              <div className="flex-1 flex flex-col gap-0.5">
                {day.segments.map((seg) => (
                  <div
                    key={seg.projectId}
                    className="rounded px-1 py-0.5 text-[10px] leading-tight"
                    style={{
                      backgroundColor: seg.projectColor + "18",
                      borderLeft: `2px solid ${seg.projectColor}`,
                    }}
                  >
                    <p className="font-medium text-foreground truncate">{seg.projectName}</p>
                    <p className="tabular-nums text-muted-foreground">
                      {seg.minutes >= 60
                        ? `${(seg.minutes / 60).toFixed(1)}h`
                        : `${Math.round(seg.minutes)}m`}
                    </p>
                  </div>
                ))}
                {/* Day total */}
                <p
                  className={cn(
                    "mt-auto pt-0.5 text-center text-[10px] font-medium tabular-nums",
                    isToday ? "text-accent" : "text-foreground/60"
                  )}
                >
                  {(day.totalMinutes / 60).toFixed(1)}h
                </p>
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center">
                <span className="text-muted-foreground/25 text-[10px]">—</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ProjectTotalsView({ data }: { data: DayProjectBreakdown[] }) {
  // Aggregate per project across all days
  const projectTotals = new Map<
    string,
    { name: string; color: string; minutes: number }
  >();
  for (const day of data) {
    for (const seg of day.segments) {
      const existing = projectTotals.get(seg.projectId);
      if (existing) {
        existing.minutes += seg.minutes;
      } else {
        projectTotals.set(seg.projectId, {
          name: seg.projectName,
          color: seg.projectColor,
          minutes: seg.minutes,
        });
      }
    }
  }

  const sorted = Array.from(projectTotals.values()).sort((a, b) => b.minutes - a.minutes);
  const maxMinutes = sorted.length > 0 ? sorted[0].minutes : 1;
  const weekTotal = sorted.reduce((sum, p) => sum + p.minutes, 0);

  if (sorted.length === 0) {
    return (
      <div className="h-32 flex items-center justify-center text-muted-foreground/40 text-xs">
        No activity this week
      </div>
    );
  }

  return (
    <div className="px-3 py-2.5 space-y-1.5">
      {sorted.map((proj) => {
        const barWidth = (proj.minutes / maxMinutes) * 100;
        const hours = proj.minutes / 60;

        return (
          <div key={proj.name} className="flex items-center gap-2">
            <div
              className="w-2 h-2 rounded-full shrink-0"
              style={{ backgroundColor: proj.color }}
            />
            <span className="text-xs text-foreground truncate min-w-0 w-24 shrink-0">
              {proj.name}
            </span>
            <div className="flex-1 h-2 rounded-full bg-muted">
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{ width: `${barWidth}%`, backgroundColor: proj.color + "B0" }}
              />
            </div>
            <span className="text-xs font-medium tabular-nums text-foreground shrink-0 w-12 text-right">
              {hours >= 1 ? `${hours.toFixed(1)}h` : `${Math.round(proj.minutes)}m`}
            </span>
          </div>
        );
      })}

      {/* Week total footer */}
      <div className="flex items-center justify-end pt-1 border-t border-border/30">
        <span className="text-[10px] uppercase tracking-widest text-muted-foreground mr-2">
          Total
        </span>
        <span className="text-sm font-medium tabular-nums text-accent">
          {formatDuration(weekTotal)}
        </span>
      </div>
    </div>
  );
}
