import { Edit2, List, Trash2 } from "lucide-react";
import { useState } from "react";
import type { Project } from "@/entities/project";
import type { Session } from "@/entities/session";
import { SessionEditForm } from "@/entities/session";
import { formatDate, formatDuration, formatTime, parseUtcIso } from "@/shared/lib";
import { EmptyState } from "@/shared/ui";

const SESSIONS_PER_PAGE = 20;

interface ProjectSessionListProps {
	/** Every session for the project, newest first. */
	sessions: Session[];
	/** Projects offered by the edit form's picker. */
	allProjects: Project[];
	/** Set when a week label in the history table is selected; null means all. */
	scopedWeeksAgo: number | null;
	/** Label for the scoped week, e.g. "This wk". */
	scopeLabel: string;
	onClearScope: () => void;
	onSave: (
		sessionId: string,
		startTime: string,
		endTime: string,
		projectId: string,
	) => Promise<void>;
	onDelete: (sessionId: string) => Promise<void>;
	isDeleting: boolean;
}

/**
 * The project page's session list: grouping, pagination, inline edit and
 * delete confirmation.
 *
 * Which session is being edited, which is pending deletion, and how many rows
 * are shown are this component's business — none of it outlives the list, and
 * the page above no longer carries the three pieces of state.
 *
 * `scopedWeeksAgo` stays a prop because the week-history table sets it and
 * this list reads it.
 */
export function ProjectSessionList({
	sessions,
	allProjects,
	scopedWeeksAgo,
	scopeLabel,
	onClearScope,
	onSave,
	onDelete,
	isDeleting,
}: ProjectSessionListProps) {
	const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
	const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
	const [visibleCount, setVisibleCount] = useState(SESSIONS_PER_PAGE);

	// Scoping to a week resets pagination so the user lands on the start of
	// that window rather than mid-list.
	const scopedSessions =
		scopedWeeksAgo === null
			? sessions
			: (() => {
					const monday = new Date();
					monday.setHours(0, 0, 0, 0);
					monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7) - scopedWeeksAgo * 7);
					const nextMonday = new Date(monday);
					nextMonday.setDate(nextMonday.getDate() + 7);
					return sessions.filter((s) => {
						const t = parseUtcIso(s.startTime);
						return t >= monday && t < nextMonday;
					});
				})();

	const visibleSessions = scopedSessions.slice(0, visibleCount);
	const hasMore = visibleCount < scopedSessions.length;

	const sessionsByDate = visibleSessions.reduce(
		(acc, session) => {
			const date = formatDate(session.startTime);
			if (!acc[date]) acc[date] = [];
			acc[date].push(session);
			return acc;
		},
		{} as Record<string, Session[]>,
	);

	const handleSave = async (
		sessionId: string,
		startTime: string,
		endTime: string,
		projectId: string,
	) => {
		await onSave(sessionId, startTime, endTime, projectId);
		setEditingSessionId(null);
	};

	const handleDelete = async (sessionId: string) => {
		await onDelete(sessionId);
		setConfirmDeleteId(null);
	};

	return (
		<section className="mt-6" aria-labelledby="sessions-heading">
			<div className="flex flex-wrap items-center gap-2 mb-3">
				<h2
					id="sessions-heading"
					className="flex items-center gap-2 text-foreground font-medium text-sm"
				>
					<List className="w-3.5 h-3.5 text-accent/75" />
					Sessions
					{sessions.length > 0 && (
						<span className="text-xs text-muted-foreground font-normal">
							({scopedSessions.length}
							{scopedWeeksAgo !== null && ` of ${sessions.length}`})
						</span>
					)}
				</h2>
				{scopedWeeksAgo !== null && (
					<button
						type="button"
						onClick={() => onClearScope()}
						className="inline-flex items-center gap-1 rounded-full border border-accent/40 bg-accent/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-accent hover:bg-accent/20 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
					>
						Scoped to {scopeLabel}
						<span aria-hidden="true">×</span>
					</button>
				)}
			</div>

			{Object.entries(sessionsByDate).length === 0 ? (
				<div className="rounded-lg border border-dashed border-border">
					<EmptyState
						variant="clock"
						message="No sessions yet. Start the timer to begin tracking."
					/>
				</div>
			) : (
				<div className="rounded-lg border border-border/80 bg-card shadow-soft overflow-hidden">
					<div className="py-1">
						{Object.entries(sessionsByDate).map(([date, dateSessions]) => {
							const dayTotalMinutes = dateSessions.reduce((sum, s) => sum + (s.duration || 0), 0);
							return (
								<div key={date}>
									{/* Date separator */}
									<div className="px-3 py-1 mt-2 first:mt-0">
										<span className="text-[10px] uppercase tracking-widest text-muted-foreground">
											{date}
										</span>
										<span className="text-[10px] text-muted-foreground/60 ml-1.5">
											— {dateSessions.length} session
											{dateSessions.length !== 1 ? "s" : ""}
											{dayTotalMinutes > 0 && (
												<span className="tabular-nums">, {formatDuration(dayTotalMinutes)}</span>
											)}
										</span>
									</div>

									{/* Session rows */}
									{dateSessions.map((session) => (
										<div key={session.id}>
											{editingSessionId === session.id ? (
												<div className="px-2 py-1">
													<SessionEditForm
														session={session}
														projects={allProjects.map((p) => ({
															id: p.id,
															name: p.name,
														}))}
														onSave={handleSave}
														onCancel={() => setEditingSessionId(null)}
													/>
												</div>
											) : (
												<div className="px-3 py-1.5 hover:bg-secondary/30 transition-colors group">
													<div className="flex items-center gap-3">
														<span className="text-sm tabular-nums text-foreground">
															{formatTime(session.startTime)} → {formatTime(session.endTime)}
														</span>
														<span
															className={`text-sm font-medium tabular-nums ml-auto ${
																session.duration > 0 ? "text-accent" : "text-muted-foreground/60"
															}`}
														>
															{session.duration > 0 ? formatDuration(session.duration) : "—"}
														</span>
														{confirmDeleteId === session.id ? (
															<div className="flex items-center gap-1">
																<button
																	type="button"
																	onClick={() => handleDelete(session.id)}
																	disabled={isDeleting}
																	className="px-1.5 py-0.5 rounded text-[11px] font-medium bg-destructive/90 text-destructive-foreground hover:bg-destructive disabled:opacity-50 transition-colors"
																>
																	Delete
																</button>
																<button
																	type="button"
																	onClick={() => setConfirmDeleteId(null)}
																	className="px-1.5 py-0.5 rounded text-[11px] text-muted-foreground hover:text-foreground transition-colors"
																>
																	Cancel
																</button>
															</div>
														) : (
															<>
																<button
																	type="button"
																	onClick={() => setEditingSessionId(session.id)}
																	className="min-h-6 min-w-6 p-1 rounded text-muted-foreground/60 hover:text-accent hover:bg-secondary/40 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
																	aria-label="Edit session"
																>
																	<Edit2 className="w-3.5 h-3.5" />
																</button>
																<button
																	type="button"
																	onClick={() => setConfirmDeleteId(session.id)}
																	className="min-h-6 min-w-6 p-1 rounded text-muted-foreground/60 hover:text-destructive hover:bg-destructive/10 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-accent/40"
																	aria-label="Delete session"
																>
																	<Trash2 className="w-3.5 h-3.5" />
																</button>
															</>
														)}
													</div>
													{(session.note || session.tags.length > 0) && (
														<div className="flex items-center gap-1.5 mt-0.5">
															{session.note && (
																<span className="text-[11px] text-muted-foreground/60 truncate">
																	{session.note}
																</span>
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
												</div>
											)}
										</div>
									))}
								</div>
							);
						})}
					</div>

					{/* Load more */}
					{hasMore && (
						<div className="border-t border-border/40">
							<button
								type="button"
								onClick={() => setVisibleCount((c) => c + SESSIONS_PER_PAGE)}
								className="w-full py-2.5 text-sm text-accent hover:bg-accent/5 transition-colors"
							>
								{/* FF.12: scope to scopedSessions, not sortedSessions —
								    when the user has clicked a week label the visible
								    list is scoped to that week's Mon..Sun range, so the
								    count must reflect what THIS click will actually
								    reveal. */}
								Show {Math.min(SESSIONS_PER_PAGE, scopedSessions.length - visibleCount)} more
								sessions...
							</button>
						</div>
					)}
				</div>
			)}
		</section>
	);
}
