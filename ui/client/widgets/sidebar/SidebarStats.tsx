/**
 * Sidebar Stats Component
 * Shows today and this week aggregate time at a glance.
 */
import { useAllCurrentWeekSessions } from "@/entities/session";

export function SidebarStats() {
  const { data: dailySummary } = useAllCurrentWeekSessions();

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const todayMinutes =
    dailySummary?.find((d) => d.date.toDateString() === today.toDateString())?.totalMinutes ?? 0;
  const weekMinutes = dailySummary?.reduce((sum, d) => sum + d.totalMinutes, 0) ?? 0;

  const todayHours = (todayMinutes / 60).toFixed(1);
  const weekHours = (weekMinutes / 60).toFixed(1);

  return (
    <div className="grid grid-cols-2 gap-2">
      <div className="rounded-md border border-border/60 bg-secondary/30 px-3 py-2.5 text-center">
        <p className="text-muted-foreground text-[10px] uppercase tracking-[0.14em] mb-0.5">Today</p>
        <p className="font-heading text-lg font-semibold tabular-nums text-foreground">
          {todayHours}h
        </p>
      </div>
      <div className="rounded-md border border-border/60 bg-secondary/30 px-3 py-2.5 text-center">
        <p className="text-muted-foreground text-[10px] uppercase tracking-[0.14em] mb-0.5">
          This week
        </p>
        <p className="font-heading text-lg font-semibold tabular-nums text-accent">
          {weekHours}h
        </p>
      </div>
    </div>
  );
}
