/**
 * AuditSection — the organisation's audit log, behind a disclosure closed
 * by default and read only once opened (the ReportLinksBlock pattern): a
 * section per page load would otherwise be a request nobody asked for.
 * Admins only.
 */

import { ChevronDown, ScrollText } from "lucide-react";
import { useState } from "react";
import { useAuditLog, useMembers, useOrgProjects } from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { formatDate } from "@/shared/lib";
import { Panel } from "@/shared/ui";
import { HEADING, HEADING_ICON, LEAD, LIST } from "./styles";

export function AuditSection({ organisationId }: { organisationId: string }) {
	const [open, setOpen] = useState(false);
	const audit = useAuditLog(organisationId, { enabled: open });
	const members = useMembers(organisationId, { enabled: open });
	const projects = useOrgProjects(organisationId, { enabled: open });

	const memberName = (userId: string) =>
		(members.data ?? []).find((m) => m.userId === userId)?.name ?? userId;
	const projectName = (projectId: string) =>
		(projects.data ?? []).find((p) => p.id === projectId)?.name ?? projectId;

	return (
		<section aria-label="Audit log" className="mb-8">
			<h2 className={HEADING}>
				<ScrollText className={HEADING_ICON} />
				Audit log
			</h2>
			<p className={`${LEAD} -mt-1 mb-3`}>
				Every membership, role, project, contract and timesheet act, since the organisation began.
			</p>
			<Panel padding="px-5 py-3">
				<button
					type="button"
					onClick={() => setOpen((o) => !o)}
					aria-expanded={open}
					className="flex items-center gap-1.5 text-[12.5px] font-bold text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring rounded-full"
				>
					<ChevronDown
						className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${open ? "" : "-rotate-90"}`}
						aria-hidden="true"
					/>
					{open ? "Hide the log" : "Show the log"}
				</button>
				{open &&
					(audit.error ? (
						<p className={`${LEAD} py-3`} role="alert">
							{describeError(audit.error, "The audit log could not be read.")}
						</p>
					) : !audit.data ? (
						<p className={`${LEAD} py-3`}>Loading…</p>
					) : audit.data.length === 0 ? (
						<p className={`${LEAD} py-3`}>Nothing yet.</p>
					) : (
						<ul className={`${LIST} mt-2`}>
							{audit.data.map((event, i) => (
								<li
									key={`${event.at}-${event.event}-${i}`}
									className="py-2 text-[12.5px] space-y-0.5"
								>
									<div className="flex items-center gap-2 flex-wrap">
										<span className="text-muted-foreground whitespace-nowrap">
											{formatDate(event.at)}
										</span>
										<span className="font-bold text-foreground">{event.event}</span>
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
					))}
			</Panel>
		</section>
	);
}
