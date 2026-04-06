/**
 * Session Card Component
 * Displays a single work session with edit button.
 */
import { Edit2 } from "lucide-react";
import { formatDuration, formatTime } from "@/shared/lib";
import type { Session } from "../model";

interface SessionCardProps {
  session: Session;
  onEdit: (session: Session) => void;
}

export function SessionCard({ session, onEdit }: SessionCardProps) {
  return (
    <div className="group flex items-center justify-between rounded-lg border border-border bg-card shadow-soft px-5 py-3.5 hover:bg-secondary/40 transition-colors duration-150">
      <div className="flex items-center gap-4 min-w-0">
        <span className="text-foreground font-medium text-base tabular-nums">
          {formatTime(session.startTime)} → {formatTime(session.endTime)}
        </span>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <span
          className={`font-medium text-base tabular-nums ${session.duration > 0 ? "text-accent" : "text-muted-foreground/60"}`}
        >
          {session.duration > 0 ? formatDuration(session.duration) : "—"}
        </span>
        <button
          onClick={() => onEdit(session)}
          className="p-1.5 rounded-md text-muted-foreground/70 hover:text-accent hover:bg-accent/5 transition-colors duration-150 focus:opacity-100 focus:outline-hidden"
          aria-label="Edit session"
        >
          <Edit2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
