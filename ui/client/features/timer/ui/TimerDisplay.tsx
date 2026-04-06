/**
 * Timer Display Component
 * Shows the current timer value.
 */
import { Clock } from "lucide-react";
import { formatSecondsToTime, parseUtcIso } from "@/shared/lib";

interface TimerDisplayProps {
  elapsedSeconds: number;
  customStartTime: string | null;
  isRunning: boolean;
  projectName?: string;
}

export function TimerDisplay({
  elapsedSeconds,
  customStartTime,
  isRunning,
  projectName,
}: TimerDisplayProps) {
  // Calculate display time
  let totalSeconds = elapsedSeconds;

  if (customStartTime && isRunning) {
    const startDate = parseUtcIso(customStartTime);
    const now = new Date();
    totalSeconds = Math.floor((now.getTime() - startDate.getTime()) / 1000);
  }

  const displayTime = formatSecondsToTime(totalSeconds);

  return (
    <div className="flex flex-col items-center py-3">
      <div className="flex items-center gap-2 mb-1">
        <Clock className="w-4 h-4 text-muted-foreground/80" />
        <span className="text-muted-foreground text-xs uppercase tracking-[0.12em]">Timer</span>
      </div>
      <p className={`font-mono text-4xl font-medium tracking-tight tabular-nums ${isRunning ? "text-accent" : "text-foreground"}`}>
        {displayTime}
      </p>
      {projectName && isRunning && (
        <p className="text-muted-foreground text-base mt-2">{projectName}</p>
      )}
      {isRunning && customStartTime && (
        <p className="text-muted-foreground text-sm mt-1">
          Started{" "}
          {parseUtcIso(customStartTime).toLocaleString(undefined, {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: true,
          })}
        </p>
      )}
    </div>
  );
}
