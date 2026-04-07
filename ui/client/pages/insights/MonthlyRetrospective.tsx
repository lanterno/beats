/**
 * MonthlyRetrospective Component
 * Full monthly summary: total hours, top project, busiest day,
 * average daily hours, longest session, tag cloud, rhythm chart.
 */
import { useMemo, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { ChevronLeft, ChevronRight, Copy, Check } from "lucide-react";
import { formatDuration, parseUtcIso } from "@/shared/lib";
import { useProjects } from "@/entities/project";
import { useDailyRhythm } from "@/entities/session";
import { fetchBeats } from "@/entities/session";
import { toSession } from "@/entities/session";
import { useQuery } from "@tanstack/react-query";
import { sessionKeys } from "@/entities/session";
import { DailyRhythmChart } from "./DailyRhythmChart";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function useMonthSessions(year: number, month: number) {
  return useQuery({
    queryKey: [...sessionKeys.all, "monthly-retro", year, month],
    queryFn: async () => {
      const beats = await fetchBeats();
      const sessions = beats
        .filter((b) => b.start && b.end)
        .map(toSession);

      return sessions.filter((s) => {
        const d = parseUtcIso(s.startTime);
        return d.getFullYear() === year && d.getMonth() === month;
      });
    },
    staleTime: 60_000,
  });
}

export default function MonthlyRetrospective() {
  const { yearMonth } = useParams<{ yearMonth: string }>();
  const navigate = useNavigate();
  const [copied, setCopied] = useState(false);

  const now = new Date();
  const [year, month] = yearMonth
    ? [parseInt(yearMonth.split("-")[0]), parseInt(yearMonth.split("-")[1]) - 1]
    : [now.getFullYear(), now.getMonth()];

  const { data: sessions, isLoading } = useMonthSessions(year, month);
  const { data: projects } = useProjects();

  const projectMap = new Map(
    (projects ?? []).map((p) => [p.id, { name: p.name, color: p.color }])
  );

  const stats = useMemo(() => {
    if (!sessions || sessions.length === 0) return null;

    const totalMinutes = sessions.reduce((sum, s) => sum + s.duration, 0);

    // Top project
    const byProject = new Map<string, number>();
    for (const s of sessions) {
      byProject.set(s.projectId, (byProject.get(s.projectId) || 0) + s.duration);
    }
    const topProjectEntry = [...byProject.entries()].sort((a, b) => b[1] - a[1])[0];
    const topProject = topProjectEntry
      ? { id: topProjectEntry[0], minutes: topProjectEntry[1], ...projectMap.get(topProjectEntry[0]) }
      : null;

    // Busiest day
    const byDay = new Map<string, number>();
    for (const s of sessions) {
      const dateKey = parseUtcIso(s.startTime).toDateString();
      byDay.set(dateKey, (byDay.get(dateKey) || 0) + s.duration);
    }
    const busiestEntry = [...byDay.entries()].sort((a, b) => b[1] - a[1])[0];
    const busiestDay = busiestEntry
      ? { date: new Date(busiestEntry[0]), minutes: busiestEntry[1] }
      : null;

    // Active days
    const activeDays = byDay.size;
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    // Average daily
    const avgDaily = totalMinutes / daysInMonth;

    // Longest session
    const longestSession = sessions.reduce(
      (max, s) => (s.duration > max.duration ? s : max),
      sessions[0]
    );

    // Tag cloud
    const tagCounts = new Map<string, number>();
    for (const s of sessions) {
      for (const tag of s.tags) {
        tagCounts.set(tag, (tagCounts.get(tag) || 0) + 1);
      }
    }
    const tagCloud = [...tagCounts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([tag, count]) => ({ tag, count }));

    // Project breakdown
    const projectBreakdown = [...byProject.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([id, minutes]) => ({
        id,
        minutes,
        name: projectMap.get(id)?.name ?? "Unknown",
        color: projectMap.get(id)?.color ?? "#888",
      }));

    return {
      totalMinutes,
      sessionCount: sessions.length,
      activeDays,
      daysInMonth,
      avgDaily,
      topProject,
      busiestDay,
      longestSession,
      tagCloud,
      projectBreakdown,
    };
  }, [sessions, projectMap, year, month]);

  const prevMonth = month === 0 ? `${year - 1}-12` : `${year}-${String(month).padStart(2, "0")}`;
  const nextMonth = month === 11 ? `${year + 1}-01` : `${year}-${String(month + 2).padStart(2, "0")}`;
  const isCurrentMonth = year === now.getFullYear() && month === now.getMonth();

  const handleCopy = () => {
    if (!stats) return;
    const lines = [
      `${MONTH_NAMES[month]} ${year} Summary`,
      `Total: ${formatDuration(stats.totalMinutes)} across ${stats.sessionCount} sessions`,
      `Active days: ${stats.activeDays}/${stats.daysInMonth}`,
      `Daily average: ${formatDuration(stats.avgDaily)}`,
      stats.topProject ? `Top project: ${stats.topProject.name} (${formatDuration(stats.topProject.minutes)})` : "",
      stats.busiestDay
        ? `Busiest day: ${stats.busiestDay.date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })} (${formatDuration(stats.busiestDay.minutes)})`
        : "",
      stats.tagCloud.length > 0 ? `Tags: ${stats.tagCloud.map((t) => t.tag).join(", ")}` : "",
    ]
      .filter(Boolean)
      .join("\n");
    navigator.clipboard.writeText(lines);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-6 space-y-5">
      {/* Navigation header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            to="/insights"
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Insights
          </Link>
          <span className="text-muted-foreground/40">/</span>
          <h1 className="font-heading text-xl text-foreground">
            {MONTH_NAMES[month]} {year}
          </h1>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => navigate(`/insights/month/${prevMonth}`)}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary/40 transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            onClick={() => navigate(`/insights/month/${nextMonth}`)}
            disabled={isCurrentMonth}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary/40 transition-colors disabled:opacity-30"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="h-40 flex items-center justify-center text-muted-foreground text-sm">
          Loading...
        </div>
      ) : !stats ? (
        <div className="h-40 flex items-center justify-center text-muted-foreground text-sm">
          No sessions recorded in {MONTH_NAMES[month]} {year}
        </div>
      ) : (
        <>
          {/* Stat cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard label="Total hours" value={formatDuration(stats.totalMinutes)} accent />
            <StatCard label="Sessions" value={String(stats.sessionCount)} />
            <StatCard label="Active days" value={`${stats.activeDays}/${stats.daysInMonth}`} />
            <StatCard label="Daily average" value={formatDuration(stats.avgDaily)} />
          </div>

          {/* Highlights */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {stats.topProject && (
              <div className="rounded-lg border border-border/60 bg-secondary/20 px-4 py-3">
                <p className="text-muted-foreground text-[10px] uppercase tracking-[0.14em] mb-1.5">
                  Top Project
                </p>
                <div className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-full shrink-0"
                    style={{ backgroundColor: stats.topProject.color }}
                  />
                  <span className="font-medium text-foreground text-sm">{stats.topProject.name}</span>
                  <span className="ml-auto text-accent font-medium text-sm tabular-nums">
                    {formatDuration(stats.topProject.minutes)}
                  </span>
                </div>
              </div>
            )}
            {stats.busiestDay && (
              <div className="rounded-lg border border-border/60 bg-secondary/20 px-4 py-3">
                <p className="text-muted-foreground text-[10px] uppercase tracking-[0.14em] mb-1.5">
                  Busiest Day
                </p>
                <div className="flex items-center justify-between">
                  <span className="font-medium text-foreground text-sm">
                    {stats.busiestDay.date.toLocaleDateString(undefined, {
                      weekday: "short",
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                  <span className="text-accent font-medium text-sm tabular-nums">
                    {formatDuration(stats.busiestDay.minutes)}
                  </span>
                </div>
              </div>
            )}
            <div className="rounded-lg border border-border/60 bg-secondary/20 px-4 py-3">
              <p className="text-muted-foreground text-[10px] uppercase tracking-[0.14em] mb-1.5">
                Longest Session
              </p>
              <div className="flex items-center justify-between">
                <span className="font-medium text-foreground text-sm">
                  {projectMap.get(stats.longestSession.projectId)?.name ?? "Unknown"}
                </span>
                <span className="text-accent font-medium text-sm tabular-nums">
                  {formatDuration(stats.longestSession.duration)}
                </span>
              </div>
            </div>
          </div>

          {/* Project breakdown */}
          {stats.projectBreakdown.length > 0 && (
            <div className="rounded-lg border border-border/80 bg-card shadow-soft p-4">
              <p className="text-sm font-medium text-foreground mb-3">Project Breakdown</p>
              <div className="space-y-2">
                {stats.projectBreakdown.map((p) => {
                  const pct = (p.minutes / stats.totalMinutes) * 100;
                  return (
                    <div key={p.id} className="flex items-center gap-2.5">
                      <div
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: p.color }}
                      />
                      <span className="text-xs text-foreground truncate w-28 shrink-0">
                        {p.name}
                      </span>
                      <div className="flex-1 h-2 rounded-full bg-muted">
                        <div
                          className="h-full rounded-full transition-all duration-300"
                          style={{
                            width: `${pct}%`,
                            backgroundColor: p.color + "B0",
                          }}
                        />
                      </div>
                      <span className="text-xs font-medium tabular-nums text-foreground w-14 text-right shrink-0">
                        {formatDuration(p.minutes)}
                      </span>
                      <span className="text-[10px] text-muted-foreground w-10 text-right shrink-0">
                        {pct.toFixed(0)}%
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Tag cloud */}
          {stats.tagCloud.length > 0 && (
            <div className="rounded-lg border border-border/80 bg-card shadow-soft p-4">
              <p className="text-sm font-medium text-foreground mb-3">Tags</p>
              <div className="flex flex-wrap gap-2">
                {stats.tagCloud.map(({ tag, count }) => (
                  <span
                    key={tag}
                    className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full bg-accent/10 text-accent"
                  >
                    {tag}
                    <span className="text-accent/50 text-[10px]">{count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Copy summary button */}
          <div className="flex justify-end">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-border bg-secondary/30 text-foreground hover:bg-secondary/60 transition-colors"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-accent" /> Copied
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" /> Copy summary
                </>
              )}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-lg border border-border/60 bg-secondary/20 px-4 py-3 text-center">
      <p className="text-muted-foreground text-[10px] uppercase tracking-[0.14em] mb-1">
        {label}
      </p>
      <p
        className={`font-heading text-lg font-semibold tabular-nums ${accent ? "text-accent" : "text-foreground"}`}
      >
        {value}
      </p>
    </div>
  );
}
