/**
 * AbsenceRequestsSection — the days off waiting on the caller's decision.
 * The note is addressed to the decider and never enters the record, which
 * the lead says. Either decision may carry a comment back; the API's own
 * words surface inside the dialog when a decision is refused (409
 * PERIOD_APPROVED while the month is locked). The names are the row's own:
 * a manager may not list the organisation's projects.
 */

import { CalendarClock } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ABSENCE_TYPE_LABELS } from "@/entities/absence";
import type { AbsenceRequest } from "@/entities/organisation";
import { useAbsenceRequests, useDecideAbsenceRequest } from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { formatDate, formatDateOnly } from "@/shared/lib";
import { Button } from "@/shared/ui";
import { CommentDialog } from "./CommentDialog";
import { memberLabel, projectLabel } from "./labels";
import { Section } from "./Section";
import { LEAD, LIST } from "./styles";

/** "Nadia · Backend · Nov 3, 2026, vacation (half day)". */
function asked(request: AbsenceRequest): string {
	const kind = (ABSENCE_TYPE_LABELS[request.type] ?? request.type).toLowerCase();
	return `${memberLabel(request.memberName)} · ${projectLabel(request.projectName)} · ${formatDateOnly(request.date)}, ${kind}${request.halfDay ? " (half day)" : ""}`;
}

export function AbsenceRequestsSection({ organisationId }: { organisationId: string }) {
	const requests = useAbsenceRequests(organisationId, { pending: true });
	const decide = useDecideAbsenceRequest(organisationId);
	const [open, setOpen] = useState<{ request: AbsenceRequest; approve: boolean } | null>(null);

	const decideNow = async (request: AbsenceRequest, approve: boolean, comment: string) => {
		await decide.mutateAsync({ requestId: request.id, approve, comment: comment || undefined });
		setOpen(null);
		toast.success(approve ? "Day off approved" : "Request declined");
	};

	return (
		<Section
			label="Absence requests"
			icon={CalendarClock}
			lead="The note is addressed to you — the record never shows it."
		>
			{requests.error ? (
				<p className={`${LEAD} py-3`} role="alert">
					{describeError(requests.error, "The requests could not be read.")}
				</p>
			) : !requests.data ? (
				<p className={`${LEAD} py-3`}>Loading…</p>
			) : requests.data.length === 0 ? (
				<p className={`${LEAD} py-3`}>Nothing waiting.</p>
			) : (
				<ul className={LIST}>
					{requests.data.map((request) => (
						<li key={request.id} className="py-2.5 text-[12.5px] space-y-1">
							<div className="flex items-center gap-2 flex-wrap">
								<span className="font-bold text-foreground">{memberLabel(request.memberName)}</span>
								<span className="text-muted-foreground">
									{projectLabel(request.projectName)} · {formatDateOnly(request.date)} ·{" "}
									{(ABSENCE_TYPE_LABELS[request.type] ?? request.type).toLowerCase()}
									{request.halfDay && " · half day"} · asked {formatDate(request.requestedAt)}
								</span>
								<span className="ml-auto flex items-center gap-2">
									<Button
										type="button"
										size="sm"
										className="h-7 px-2.5 text-xs"
										onClick={() => setOpen({ request, approve: true })}
										disabled={decide.isPending}
										aria-label={`Approve ${asked(request)}`}
									>
										Approve
									</Button>
									<Button
										type="button"
										variant="secondary"
										size="sm"
										className="h-7 px-2.5 text-xs hover:text-destructive-ink"
										onClick={() => setOpen({ request, approve: false })}
										disabled={decide.isPending}
										aria-label={`Decline ${asked(request)}`}
									>
										Decline
									</Button>
								</span>
							</div>
							{request.note && <p className="text-muted-foreground">“{request.note}”</p>}
						</li>
					))}
				</ul>
			)}
			{open && (
				<CommentDialog
					key={`${open.request.id}-${open.approve}`}
					title={open.approve ? "Approve this day off?" : "Decline this day off?"}
					context={asked(open.request)}
					hint={open.request.note ? <p className={LEAD}>“{open.request.note}”</p> : undefined}
					commentLabel={open.approve ? "Comment (optional)" : "Comment (recommended)"}
					confirmLabel={open.approve ? "Approve" : "Decline"}
					busyLabel="Sending…"
					danger={!open.approve}
					onClose={() => setOpen(null)}
					onSend={(comment) => decideNow(open.request, open.approve, comment)}
				/>
			)}
		</Section>
	);
}
