/**
 * DailyRhythmChart Component
 * 24-hour bar chart showing when you typically work.
 */
import { useState } from "react";
import { cn } from "@/shared/lib";
import { useDailyRhythm } from "@/entities/session";

type Period = "week" | "month" | "all";

const PERIOD_LABELS: Record<Period, string> = {
  week: "This Week",
  month: "This Month",
  all: "All Time",
};

const HOUR_LABELS = [0, 3, 6, 9, 12, 15, 18, 21];

export function DailyRhythmChart() {
  const [period, setPeriod] = useState<Period>("month");
  const { data: rhythmData, isLoading } = useDailyRhythm(period);

  const slots = rhythmData ?? [];
  const maxMinutes = Math.max(...slots.map((s) => s.minutes), 1);

  return (
    <div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/40">
        <span className="text-sm font-medium text-foreground">Daily Rhythm</span>
        <div className="flex rounded-md border border-border overflow-hidden">
          {(["week", "month", "all"] as Period[]).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={cn(
                "px-2.5 py-1 text-xs transition-colors",
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

      {/* Chart */}
      <div className="px-4 py-4">
        {isLoading ? (
          <div className="h-28 flex items-center justify-center text-muted-foreground text-xs">
            Loading...
          </div>
        ) : (
          <div>
            {/* Bars */}
            <div className="flex items-end gap-px h-28">
              {slots.map((slot) => {
                const height = slot.minutes > 0 ? Math.max((slot.minutes / maxMinutes) * 100, 2) : 0;
                const hour = Math.floor(slot.slot / 2);
                const half = slot.slot % 2 === 0 ? "00" : "30";

                return (
                  <div
                    key={slot.slot}
                    className="flex-1 flex items-end justify-center"
                    title={`${hour}:${half} — ${slot.minutes.toFixed(1)} min avg`}
                  >
                    <div
                      className={cn(
                        "w-full rounded-t-sm transition-all",
                        slot.minutes > 0 ? "bg-accent/60" : "bg-transparent"
                      )}
                      style={{ height: `${height}%` }}
                    />
                  </div>
                );
              })}
            </div>

            {/* Hour labels */}
            <div className="flex mt-1.5">
              {Array.from({ length: 48 }, (_, i) => {
                const hour = Math.floor(i / 2);
                const isLabeled = HOUR_LABELS.includes(hour) && i % 2 === 0;
                return (
                  <div key={i} className="flex-1 text-center">
                    {isLabeled && (
                      <span className="text-[9px] tabular-nums text-muted-foreground">
                        {hour}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
