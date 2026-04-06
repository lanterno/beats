/**
 * WeekBar Component
 * Compact horizontal strip showing 7 days of the current week with proportional bars.
 */
import { cn } from "@/shared/lib";
import { useAllCurrentWeekSessions } from "@/entities/session";

export function WeekBar() {
  const { data: dailySummary, isLoading } = useAllCurrentWeekSessions();

  if (isLoading || !dailySummary) {
    return (
      <div className="rounded-lg border border-border/80 bg-card shadow-soft p-3 h-[60px] flex items-center justify-center">
        <span className="text-muted-foreground text-xs">Loading week...</span>
      </div>
    );
  }

  const maxDayMinutes = Math.max(...dailySummary.map((d) => d.totalMinutes), 1);
  const weekTotal = dailySummary.reduce((sum, d) => sum + d.totalMinutes, 0);
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  return (
    <div className="rounded-lg border border-border/80 bg-card shadow-soft p-3">
      <div className="flex items-center gap-1">
        {dailySummary.map((day) => {
          const isToday = day.date.toDateString() === today.toDateString();
          const hours = day.totalMinutes / 60;
          const barWidth = day.totalMinutes > 0 ? (day.totalMinutes / maxDayMinutes) * 100 : 0;

          return (
            <div
              key={day.dayName}
              className={cn(
                "flex-1 rounded-md px-1.5 py-1.5 text-center min-w-0",
                isToday && "ring-1 ring-accent/40 bg-accent/5"
              )}
            >
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground leading-none">
                {day.dayName.slice(0, 3)}
              </p>
              <p
                className={cn(
                  "text-sm font-medium tabular-nums leading-tight mt-0.5",
                  day.totalMinutes > 0
                    ? isToday
                      ? "text-accent"
                      : "text-foreground"
                    : "text-muted-foreground/40"
                )}
              >
                {hours > 0 ? `${hours.toFixed(1)}h` : "—"}
              </p>
              <div className="h-1 rounded-full bg-muted mt-1">
                <div
                  className={cn(
                    "h-full rounded-full transition-all duration-300",
                    isToday ? "bg-accent" : "bg-accent/60"
                  )}
                  style={{ width: `${barWidth}%` }}
                />
              </div>
            </div>
          );
        })}

        {/* Week total */}
        <div className="shrink-0 pl-3 border-l border-border/50 text-right min-w-[56px]">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground leading-none">
            Week
          </p>
          <p className="text-base font-heading font-semibold tabular-nums text-accent leading-tight mt-0.5">
            {weekTotal > 0 ? `${(weekTotal / 60).toFixed(1)}h` : "0h"}
          </p>
        </div>
      </div>
    </div>
  );
}
