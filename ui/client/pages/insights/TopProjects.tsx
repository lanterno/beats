/**
 * TopProjects Component
 * Horizontal bar chart showing hours per project for a period.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { cn, formatDuration } from "@/shared/lib";
import { EmptyState } from "@/shared/ui";
import { useProjects } from "@/entities/project";
import { useProjectBreakdown } from "@/entities/session";

type Period = "week" | "month" | "year" | "all";

const PERIOD_LABELS: Record<Period, string> = {
  week: "This Week",
  month: "This Month",
  year: "This Year",
  all: "All Time",
};

export function TopProjects() {
  const navigate = useNavigate();
  const [period, setPeriod] = useState<Period>("month");
  const { data: breakdown, isLoading } = useProjectBreakdown(period);
  const { data: projects } = useProjects();

  const projectMap = new Map(
    (projects ?? []).map((p) => [p.id, { name: p.name, color: p.color }])
  );

  const items = (breakdown ?? [])
    .map((b) => {
      const proj = projectMap.get(b.projectId);
      if (!proj) return null;
      return { ...b, name: proj.name, color: proj.color };
    })
    .filter(Boolean) as Array<{ projectId: string; minutes: number; name: string; color: string }>;

  const maxMinutes = items.length > 0 ? items[0].minutes : 1;
  const totalMinutes = items.reduce((sum, i) => sum + i.minutes, 0);

  return (
    <div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/40">
        <span className="text-sm font-medium text-foreground">Top Projects</span>
        <div className="flex rounded-md border border-border overflow-hidden">
          {(["week", "month", "year", "all"] as Period[]).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={cn(
                "px-2 py-1 text-xs transition-colors",
                p !== "week" && "border-l border-border",
                period === p
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
              )}
            >
              {PERIOD_LABELS[p]}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="px-4 py-3">
        {isLoading ? (
          <div className="h-20 flex items-center justify-center text-muted-foreground text-xs">
            Loading...
          </div>
        ) : items.length === 0 ? (
          <EmptyState variant="seedling" message="Track some time to see your project breakdown" />
        ) : (
          <div className="space-y-2">
            {items.map((item) => {
              const barWidth = (item.minutes / maxMinutes) * 100;

              return (
                <button
                  key={item.projectId}
                  onClick={() => navigate(`/project/${item.projectId}`)}
                  className="w-full flex items-center gap-2.5 hover:bg-secondary/30 -mx-1.5 px-1.5 py-0.5 rounded transition-colors"
                >
                  <div
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: item.color }}
                  />
                  <span className="text-xs text-foreground truncate min-w-0 w-28 shrink-0 text-left">
                    {item.name}
                  </span>
                  <div className="flex-1 h-2 rounded-full bg-muted">
                    <div
                      className="h-full rounded-full transition-all duration-300"
                      style={{ width: `${barWidth}%`, backgroundColor: item.color + "B0" }}
                    />
                  </div>
                  <span className="text-xs font-medium tabular-nums text-foreground shrink-0 w-14 text-right">
                    {formatDuration(item.minutes)}
                  </span>
                </button>
              );
            })}

            {/* Total footer */}
            <div className="flex items-center justify-end pt-1.5 border-t border-border/30">
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground mr-2">
                Total
              </span>
              <span className="text-sm font-medium tabular-nums text-accent">
                {formatDuration(totalMinutes)}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
