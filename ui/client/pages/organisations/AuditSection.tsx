/**
 * AuditSection — the organisation's audit log, behind a disclosure closed
 * by default and read only once opened (the ReportLinksBlock pattern): a
 * section per page load would otherwise be a request nobody asked for.
 * Each line says when (to the minute — same-day acts must order), who did
 * it, what in words rather than an event code, and to whom; the API pages
 * at 100, so a full page ends in "Show earlier". Admins only.
 */

import { ChevronDown, ScrollText } from "lucide-react";
import { useId, useState } from "react";
import type { AuditEvent } from "@/entities/organisation";
import { useAuditLog, useMembers, useOrgProjects } from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { formatDate, formatTime } from "@/shared/lib";
import { Button } from "@/shared/ui";
import { Section } from "./Section";
import { LEAD, LIST } from "./styles";

/** "timesheet.approved" → "Timesheet approved" — words, not a code. */
function eventWords(event: string): string {
	const words = event.split(".").join(" ").split("_").join(" ");
	return words.charAt(0).toUpperCase() + words.slice(1);
}

export function AuditSection({ organisationId }: { organisationId: string }) {
	const id = useId();
	const [open, setOpen] = useState(false);
	const audit = useAuditLog(organisationId, { enabled: open });
	const members = useMembers(organisationId, { enabled: open });
	const projects = useOrgProjects(organisationId, { enabled: open });

	const memberName = (userId: string) =>
		(members.data ?? []).find((m) => m.userId === userId)?.name ?? "a former member";
	const projectName = (projectId: string) =>
		(projects.data ?? []).find((p) => p.id === projectId)?.name ?? "a project";

	const events: AuditEvent[] = audit.data?.pages?.flat() ?? [];

	return (
		<Section
			label="Audit log"
			icon={ScrollText}
			lead="Every membership, role, project, contract and timesheet act, since the organisation began."
			bodyClassName="px-5 py-3"
		>
			<button
				type="button"
				onClick={() => setOpen((o) => !o)}
				aria-expanded={open}
				aria-controls={`${id}-log`}
				className="flex items-center gap-1.5 text-[12.5px] font-bold text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring rounded-full"
			>
				<ChevronDown
					className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${open ? "" : "-rotate-90"}`}
					aria-hidden="true"
				/>
				{open ? "Hide the log" : "Show the log"}
			</button>
			<div id={`${id}-log`}>
				{open &&
					(audit.error ? (
						<p className={`${LEAD} py-3`} role="alert">
							{describeError(audit.error, "The audit log could not be read.")}
						</p>
					) : !audit.data ? (
						<p className={`${LEAD} py-3`}>Loading…</p>
					) : events.length === 0 ? (
						<p className={`${LEAD} py-3`}>Nothing yet.</p>
					) : (
						<>
							<ul className={`${LIST} mt-2`}>
								{events.map((event, i) => (
									<li
										key={`${event.at}-${event.event}-${i}`}
										className="py-2 text-[12.5px] space-y-0.5"
									>
										<div className="flex items-center gap-2 flex-wrap">
											<span className="text-muted-foreground whitespace-nowrap">
												{formatDate(event.at)}, {formatTime(event.at)}
											</span>
											<span className="font-bold text-foreground">{eventWords(event.event)}</span>
											{event.subjectUserId && (
												<span className="text-muted-foreground">
													{memberName(event.subjectUserId)}
												</span>
											)}
											{event.projectId && (
												<span className="text-muted-foreground">
													· {projectName(event.projectId)}
												</span>
											)}
											{event.actorUserId && (
												<span className="text-muted-foreground">
													· by {memberName(event.actorUserId)}
												</span>
											)}
										</div>
										{Object.keys(event.details).length > 0 && (
											<p className="text-muted-foreground">
												{Object.entries(event.details)
													.map(([k, v]) => `${k}: ${String(v)}`)
													.join(" · ")}
											</p>
										)}
									</li>
								))}
							</ul>
							{audit.hasNextPage && (
								<Button
									type="button"
									variant="secondary"
									size="sm"
									className="mt-2"
									onClick={() => void audit.fetchNextPage()}
									disabled={audit.isFetchingNextPage}
								>
									{audit.isFetchingNextPage ? "Reading…" : "Show earlier"}
								</Button>
							)}
						</>
					))}
			</div>
		</Section>
	);
}
