/**
 * SessionTimeline Component
 * Horizontal timeline showing sessions as colored blocks on a 24h axis.
 * One row per day, most recent on top.
 */
import { useMemo } from "react";
import type { Session } from "@/entities/session";
import { formatTime, parseUtcIso } from "@/shared/lib";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/shared/ui";

interface SessionTimelineProps {
	sessions: Session[];
	projectColor: string;
}

const HOUR_LABELS = [0, 6, 12, 18, 24];

export function SessionTimeline({ sessions, projectColor }: SessionTimelineProps) {
	// Group sessions by date, most recent first
	const dayRows = useMemo(() => {
		const byDate = new Map<string, Session[]>();
		for (const s of sessions) {
			if (s.duration <= 0) continue;
			const date = parseUtcIso(s.startTime).toLocaleDateString("en-CA"); // YYYY-MM-DD
			const list = byDate.get(date) ?? [];
			list.push(s);
			byDate.set(date, list);
		}
		return Array.from(byDate.entries())
			.sort((a, b) => b[0].localeCompare(a[0]))
			.slice(0, 14); // Show last 14 days with activity
	}, [sessions]);

	if (dayRows.length === 0) return null;

	return (
		<section className="mt-6" aria-label="Session timeline">
			<h2 className="text-foreground font-medium text-sm mb-3">Timeline</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden">
				{/* Hour labels */}
				<div className="flex items-center px-3 py-1.5 border-b border-border/40">
					<div className="w-20 shrink-0" />
					<div className="flex-1 flex justify-between">
						{HOUR_LABELS.map((h) => (
							<span key={h} className="text-[9px] tabular-nums text-muted-foreground/50">
								{h === 24 ? "" : `${h}h`}
							</span>
						))}
					</div>
				</div>

				{/* Day rows */}
				{dayRows.map(([date, daySessions]) => {
					const dateObj = new Date(date);
					const label = dateObj.toLocaleDateString("en-US", {
						weekday: "short",
						month: "short",
						day: "numeric",
					});

					return (
						<div
							key={date}
							className="flex items-center px-3 py-1 border-b border-border/10 last:border-b-0 hover:bg-secondary/10"
						>
							<span className="w-20 shrink-0 text-[10px] text-muted-foreground truncate">
								{label}
							</span>
							<div className="flex-1 h-3 relative bg-muted/30 rounded-sm">
								{daySessions.map((session) => {
									const start = parseUtcIso(session.startTime);
									const end = parseUtcIso(session.endTime);
									const startMinutes = start.getHours() * 60 + start.getMinutes();
									const endMinutes = end.getHours() * 60 + end.getMinutes();
									const left = (startMinutes / 1440) * 100;
									const width = Math.max(((endMinutes - startMinutes) / 1440) * 100, 0.5);

									return (
										<Tooltip key={session.id}>
											<TooltipTrigger asChild>
												<div
													className="absolute top-0 h-full rounded-sm cursor-default"
													style={{
														left: `${left}%`,
														width: `${width}%`,
														backgroundColor: `${projectColor}B0`,
													}}
												/>
											</TooltipTrigger>
											<TooltipContent side="top" className="text-xs px-2.5 py-1.5">
												<p className="font-medium">
													{formatTime(session.startTime)} → {formatTime(session.endTime)}
												</p>
												<p className="text-muted-foreground mt-0.5">
													{Math.round(session.duration)}m
												</p>
												{session.note && (
													<p className="text-muted-foreground/70 mt-0.5 max-w-[200px] truncate">
														{session.note}
													</p>
												)}
											</TooltipContent>
										</Tooltip>
									);
								})}
							</div>
						</div>
					);
				})}
			</div>
		</section>
	);
}
