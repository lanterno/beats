/**
 * Sidebar Timer Component
 * Vertical timer card with prominent display and full-width controls.
 */
import { useState } from "react";
import { Play, Square, Calendar } from "lucide-react";
import { toast } from "sonner";
import { cn, formatSecondsToTime, parseUtcIso, toLocalDatetimeLocalString } from "@/shared/lib";
import type { ProjectWithDuration } from "@/entities/project";

export interface TimerProps {
  projects: ProjectWithDuration[];
  isRunning: boolean;
  selectedProjectId: string | null;
  elapsedSeconds: number;
  customStartTime: string | null;
  startTimer: (projectId: string, startTime?: string) => void;
  stopTimer: () => void;
  selectProject: (projectId: string | null) => void;
  setCustomStartTime: (startTime: string | null) => void;
}

export function SidebarTimer({
  projects,
  isRunning,
  selectedProjectId,
  elapsedSeconds,
  customStartTime,
  startTimer,
  stopTimer,
  selectProject,
  setCustomStartTime,
}: TimerProps) {
  const [showStartTimeInput, setShowStartTimeInput] = useState(false);

  const selectedProject = projects.find((p) => p.id === selectedProjectId);

  let totalSeconds = elapsedSeconds;
  if (customStartTime && isRunning) {
    const startDate = parseUtcIso(customStartTime);
    const now = new Date();
    totalSeconds = Math.floor((now.getTime() - startDate.getTime()) / 1000);
  }

  const handleStart = () => {
    if (selectedProjectId) {
      if (showStartTimeInput && customStartTime) {
        startTimer(selectedProjectId, customStartTime);
      } else {
        startTimer(selectedProjectId);
      }
      setShowStartTimeInput(false);
    }
  };

  const handleStop = () => {
    const projectName = selectedProject?.name;
    let minutes = Math.floor(elapsedSeconds / 60);
    if (customStartTime) {
      const startDate = parseUtcIso(customStartTime);
      const now = new Date();
      minutes = Math.floor((now.getTime() - startDate.getTime()) / 1000 / 60);
    }
    stopTimer();
    setShowStartTimeInput(false);
    setCustomStartTime(null);
    if (projectName) {
      toast.success(`Logged ${minutes}m to ${projectName}`);
    }
  };

  return (
    <div
      className={cn(
        "rounded-lg border p-4 transition-all duration-300",
        isRunning
          ? "border-accent/30 bg-accent/5 shadow-glow-amber"
          : "border-border bg-card"
      )}
    >
      {/* Timer display */}
      <div className="text-center mb-3">
        <p
          className={cn(
            "font-mono text-3xl font-semibold tabular-nums tracking-tight",
            isRunning ? "text-accent" : "text-muted-foreground/60"
          )}
        >
          {formatSecondsToTime(totalSeconds)}
        </p>
        {isRunning && selectedProject && (
          <div className="flex items-center justify-center gap-1.5 mt-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
            <div
              className="w-2 h-2 rounded-full shrink-0"
              style={{ backgroundColor: selectedProject.color }}
            />
            <span className="text-foreground text-sm font-medium truncate max-w-[140px]">
              {selectedProject.name}
            </span>
          </div>
        )}
      </div>

      {/* Project selector (when not running) */}
      {!isRunning && (
        <div className="mb-3">
          <select
            value={selectedProjectId || ""}
            onChange={(e) => selectProject(e.target.value || null)}
            className="w-full rounded-md border border-border bg-background py-2 px-3 text-sm text-foreground focus:outline-hidden focus:ring-1 focus:ring-accent/30 focus:border-accent/40"
          >
            <option value="">Select project...</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Action button */}
      {isRunning ? (
        <button
          onClick={handleStop}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-sm font-medium bg-destructive text-destructive-foreground hover:bg-destructive/85 transition-colors"
        >
          <Square className="w-3.5 h-3.5" />
          Stop
        </button>
      ) : (
        <div className="space-y-2">
          <button
            onClick={handleStart}
            disabled={!selectedProjectId}
            className={cn(
              "w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-sm font-medium transition-colors",
              !selectedProjectId
                ? "bg-muted text-muted-foreground cursor-not-allowed"
                : "bg-accent text-accent-foreground hover:bg-accent/85"
            )}
          >
            <Play className="w-3.5 h-3.5" />
            Start
          </button>

          {selectedProjectId && (
            <div className="flex items-center gap-1">
              <button
                onClick={() => {
                  setShowStartTimeInput(!showStartTimeInput);
                  if (!showStartTimeInput && !customStartTime) {
                    setCustomStartTime(new Date(Date.now() - 60 * 60 * 1000).toISOString());
                  }
                }}
                className={cn(
                  "p-1.5 rounded-md text-muted-foreground hover:text-accent hover:bg-accent/5 transition-colors text-xs flex items-center gap-1",
                  showStartTimeInput && "text-accent bg-accent/5"
                )}
              >
                <Calendar className="w-3 h-3" />
                Custom start
              </button>
            </div>
          )}

          {showStartTimeInput && (
            <input
              type="datetime-local"
              value={
                customStartTime
                  ? toLocalDatetimeLocalString(new Date(customStartTime))
                  : toLocalDatetimeLocalString(new Date(Date.now() - 60 * 60 * 1000))
              }
              onChange={(e) => {
                const date = new Date(e.target.value);
                setCustomStartTime(date.toISOString());
              }}
              className="w-full rounded-md border border-border bg-background py-1.5 px-2 text-sm text-foreground focus:outline-hidden focus:ring-1 focus:ring-accent/30"
            />
          )}
        </div>
      )}
    </div>
  );
}
