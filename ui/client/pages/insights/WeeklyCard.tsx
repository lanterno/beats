/**
 * WeeklyCard Component
 * Shareable visual summary card rendered as an SVG-styled div.
 * Shows project breakdown, hours, streak, and goal completion.
 */
import { useRef, useMemo, useState } from "react";
import { Copy, Check } from "lucide-react";
import { toast } from "sonner";
import { formatDuration, getWeekRange, parseUtcIso, getDayName } from "@/shared/lib";
import { useProjects } from "@/entities/project";
import { useStreaks, useThisWeekSessions } from "@/entities/session";

export function WeeklyCard() {
  const cardRef = useRef<HTMLDivElement>(null);
  const { data: projects } = useProjects();
  const { data: weekSessions } = useThisWeekSessions();
  const { data: streaks } = useStreaks();

  const projectMap = new Map(
    (projects ?? []).map((p) => [p.id, { name: p.name, color: p.color }])
  );

  const stats = useMemo(() => {
    const sessions = weekSessions ?? [];
    const totalMinutes = sessions.reduce((sum, s) => sum + s.duration, 0);
    const sessionCount = sessions.length;

    // By project
    const byProject = new Map<string, number>();
    for (const s of sessions) {
      byProject.set(s.projectId, (byProject.get(s.projectId) || 0) + s.duration);
    }
    const projectBreakdown = [...byProject.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([id, minutes]) => ({
        id,
        minutes,
        name: projectMap.get(id)?.name ?? "Unknown",
        color: projectMap.get(id)?.color ?? "#888",
      }));

    // Day breakdown for mini chart
    const { start: weekStart } = getWeekRange(0);
    const dayMinutes = Array.from({ length: 7 }, (_, i) => {
      const d = new Date(weekStart);
      d.setDate(weekStart.getDate() + i);
      d.setHours(0, 0, 0, 0);
      const dEnd = new Date(d);
      dEnd.setHours(23, 59, 59, 999);
      return sessions
        .filter((s) => {
          const sd = parseUtcIso(s.startTime);
          return sd >= d && sd <= dEnd;
        })
        .reduce((sum, s) => sum + s.duration, 0);
    });

    // Goals
    const goalsMetCount = (projects ?? []).filter((p) => {
      if (!p.weeklyGoal || p.archived) return false;
      const projectMinutes = byProject.get(p.id) ?? 0;
      return projectMinutes >= p.weeklyGoal * 60;
    }).length;
    const goalsTotal = (projects ?? []).filter((p) => p.weeklyGoal && !p.archived).length;

    return { totalMinutes, sessionCount, projectBreakdown, dayMinutes, goalsMetCount, goalsTotal };
  }, [weekSessions, projects, projectMap]);

  const { start: weekStart, end: weekEnd } = getWeekRange(0);
  const weekLabel = `${weekStart.toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${weekEnd.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;

  const maxDayMinutes = Math.max(...stats.dayMinutes, 1);
  const dayLabels = ["M", "T", "W", "T", "F", "S", "S"];

  const [isCopied, setIsCopied] = useState(false);

  const handleCopy = () => {
    const lines = [
      `Weekly Summary — ${weekLabel}`,
      `Total: ${formatDuration(stats.totalMinutes)} (${stats.sessionCount} sessions)`,
      streaks && streaks.current > 0 ? `Streak: ${streaks.current} days` : "",
      "",
      ...stats.projectBreakdown.slice(0, 5).map((p) => `  ${p.name}: ${formatDuration(p.minutes)}`),
      stats.goalsTotal > 0 ? `\nGoals: ${stats.goalsMetCount}/${stats.goalsTotal} met` : "",
    ].filter(Boolean).join("\n");
    navigator.clipboard.writeText(lines);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
    toast.success("Summary copied to clipboard");
  };

  return (
    <div className="space-y-3">
      {/* The card */}
      <div
        ref={cardRef}
        className="rounded-xl border border-border/80 bg-card shadow-soft p-6 max-w-sm mx-auto"
      >
        {/* Header */}
        <div className="text-center mb-4">
          <p className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground mb-0.5">
            Weekly Summary
          </p>
          <p className="text-xs text-muted-foreground/70">{weekLabel}</p>
        </div>

        {/* Big number */}
        <div className="text-center mb-4">
          <p className="font-heading text-3xl font-bold text-accent tabular-nums">
            {formatDuration(stats.totalMinutes)}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {stats.sessionCount} session{stats.sessionCount !== 1 ? "s" : ""}
            {streaks && streaks.current > 0 && (
              <span className="ml-2 text-accent/80">{streaks.current}-day streak</span>
            )}
          </p>
        </div>

        {/* Mini day chart */}
        <div className="flex items-end justify-center gap-1.5 h-12 mb-4">
          {stats.dayMinutes.map((minutes, i) => (
            <div key={i} className="flex flex-col items-center gap-0.5">
              <div
                className="w-5 rounded-sm transition-all"
                style={{
                  height: `${Math.max((minutes / maxDayMinutes) * 40, 2)}px`,
                  backgroundColor: minutes > 0 ? "var(--accent)" : "var(--muted)",
                  opacity: minutes > 0 ? 0.8 : 0.3,
                }}
              />
              <span className="text-[8px] text-muted-foreground/60">{dayLabels[i]}</span>
            </div>
          ))}
        </div>

        {/* Project breakdown */}
        {stats.projectBreakdown.length > 0 && (
          <div className="space-y-1.5 mb-3">
            {stats.projectBreakdown.slice(0, 5).map((p) => (
              <div key={p.id} className="flex items-center gap-2">
                <div
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ backgroundColor: p.color }}
                />
                <span className="text-xs text-foreground truncate flex-1">{p.name}</span>
                <span className="text-xs font-medium tabular-nums text-foreground">
                  {formatDuration(p.minutes)}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Goals */}
        {stats.goalsTotal > 0 && (
          <div className="text-center pt-2 border-t border-border/30">
            <p className="text-xs text-muted-foreground">
              Goals: <span className="text-accent font-medium">{stats.goalsMetCount}/{stats.goalsTotal}</span> met
            </p>
          </div>
        )}

        {/* Branding */}
        <div className="text-center mt-3">
          <p className="text-[9px] text-muted-foreground/40 tracking-widest uppercase">Beats</p>
        </div>
      </div>

      {/* Actions */}
      <div className="flex justify-center gap-2">
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-border bg-secondary/30 text-foreground hover:bg-secondary/60 transition-colors"
        >
          {isCopied ? (
            <><Check className="w-3.5 h-3.5 text-accent" /> Copied</>
          ) : (
            <><Copy className="w-3.5 h-3.5" /> Copy summary</>
          )}
        </button>
      </div>
    </div>
  );
}
