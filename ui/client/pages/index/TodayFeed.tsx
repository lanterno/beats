/**
 * TodayFeed Component
 * Today's sessions listed compactly, with collapsible yesterday/earlier sections.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, Clock } from "lucide-react";
import { cn, formatTime, formatDuration, parseUtcIso } from "@/shared/lib";
import { useTodaySessions, useThisWeekSessions } from "@/entities/session";
import { useProjects } from "@/entities/project";
import type { Session } from "@/entities/session";

function SessionRow({
  session,
  projectName,
  projectColor,
  projectId,
}: {
  session: Session;
  projectName: string;
  projectColor: string;
  projectId: string;
}) {
  const navigate = useNavigate();

  return (
    <button
      onClick={() => navigate(`/project/${projectId}`)}
      className="w-full flex flex-col px-3 py-1.5 hover:bg-secondary/30 rounded-md transition-colors text-left"
    >
      <div className="flex items-center gap-2">
        <div
          className="w-1.5 h-1.5 rounded-full shrink-0"
          style={{ backgroundColor: projectColor }}
        />
        <span className="text-sm text-foreground truncate flex-1 min-w-0">
          {projectName}
        </span>
        <span className="text-xs text-muted-foreground tabular-nums shrink-0">
          {formatTime(session.startTime)} → {formatTime(session.endTime)}
        </span>
        <span className="text-sm font-medium tabular-nums text-foreground w-14 text-right shrink-0">
          {session.duration > 0 ? formatDuration(session.duration) : "—"}
        </span>
      </div>
      {(session.note || session.tags.length > 0) && (
        <div className="flex items-center gap-1.5 ml-4 mt-0.5">
          {session.note && (
            <span className="text-[11px] text-muted-foreground/70 truncate">{session.note}</span>
          )}
          {session.tags.map((tag) => (
            <span
              key={tag}
              className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent/10 text-accent/70"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </button>
  );
}

function SessionGroup({
  label,
  sessions,
  totalMinutes,
  projectMap,
  defaultOpen,
}: {
  label: string;
  sessions: Session[];
  totalMinutes: number;
  projectMap: Map<string, { name: string; color: string }>;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  if (sessions.length === 0) return null;

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-secondary/20 rounded-md transition-colors"
      >
        <ChevronDown
          className={cn(
            "w-3 h-3 text-muted-foreground transition-transform duration-150",
            !open && "-rotate-90"
          )}
        />
        <span className="text-xs uppercase tracking-[0.1em] text-muted-foreground font-medium">
          {label}
        </span>
        <span className="text-xs text-muted-foreground/60">
          — {sessions.length} session{sessions.length !== 1 ? "s" : ""}
        </span>
        <span className="ml-auto text-xs font-medium tabular-nums text-muted-foreground">
          {formatDuration(totalMinutes)}
        </span>
      </button>
      {open && (
        <div className="mt-0.5">
          {sessions.map((session) => {
            const info = projectMap.get(session.projectId);
            return (
              <SessionRow
                key={session.id}
                session={session}
                projectName={info?.name || "Unknown"}
                projectColor={info?.color || "#888"}
                projectId={session.projectId}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

export function TodayFeed() {
  const { data: todaySessions } = useTodaySessions();
  const { data: weekSessions } = useThisWeekSessions();
  const { data: projects } = useProjects();

  const projectMap = new Map(
    (projects || []).map((p) => [p.id, { name: p.name, color: p.color }])
  );

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  // Split week sessions into yesterday and earlier (excluding today)
  const yesterdaySessions = (weekSessions || []).filter((s) => {
    const d = parseUtcIso(s.startTime);
    return d >= yesterday && d < today;
  });

  const earlierSessions = (weekSessions || []).filter((s) => {
    const d = parseUtcIso(s.startTime);
    return d < yesterday;
  });

  const todayTotal = (todaySessions || []).reduce((sum, s) => sum + s.duration, 0);
  const yesterdayTotal = yesterdaySessions.reduce((sum, s) => sum + s.duration, 0);
  const earlierTotal = earlierSessions.reduce((sum, s) => sum + s.duration, 0);

  const todayList = todaySessions || [];

  return (
    <div>
      <h2 className="flex items-center gap-2 text-foreground font-medium text-sm mb-3">
        <Clock className="w-3.5 h-3.5 text-accent/75" />
        Activity
      </h2>

      <div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden">
        {/* Today section — always open */}
        <div className="px-1 py-2">
          <div className="flex items-center gap-2 px-3 py-1 mb-0.5">
            <span className="text-xs uppercase tracking-[0.1em] text-accent font-semibold">
              Today
            </span>
            {todayList.length > 0 && (
              <span className="text-xs text-muted-foreground/60">
                — {todayList.length} session{todayList.length !== 1 ? "s" : ""}
              </span>
            )}
            <span className="ml-auto text-sm font-medium tabular-nums text-accent">
              {todayTotal > 0 ? formatDuration(todayTotal) : "0m"}
            </span>
          </div>

          {todayList.length > 0 ? (
            todayList.map((session) => {
              const info = projectMap.get(session.projectId);
              return (
                <SessionRow
                  key={session.id}
                  session={session}
                  projectName={info?.name || "Unknown"}
                  projectColor={info?.color || "#888"}
                  projectId={session.projectId}
                />
              );
            })
          ) : (
            <div className="px-3 py-4 text-center">
              <p className="text-muted-foreground/60 text-xs">
                No sessions yet. Start the timer to begin tracking.
              </p>
            </div>
          )}
        </div>

        {/* Yesterday + Earlier — collapsible */}
        {(yesterdaySessions.length > 0 || earlierSessions.length > 0) && (
          <div className="border-t border-border/40 px-1 py-1.5">
            <SessionGroup
              label="Yesterday"
              sessions={yesterdaySessions}
              totalMinutes={yesterdayTotal}
              projectMap={projectMap}
              defaultOpen={false}
            />
            <SessionGroup
              label="Earlier this week"
              sessions={earlierSessions}
              totalMinutes={earlierTotal}
              projectMap={projectMap}
              defaultOpen={false}
            />
          </div>
        )}
      </div>
    </div>
  );
}
