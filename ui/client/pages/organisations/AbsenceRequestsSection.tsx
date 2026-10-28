/**
 * AbsenceRequestsSection — the days off waiting on the caller's decision.
 * The note is addressed to the decider and never enters the record, which
 * the lead says. Either decision may carry a comment back; the API's own
 * words surface inside the dialog when a decision is refused (409
 * PERIOD_APPROVED while the month is locked). The names are the row's own:
 * a manager may not list the organisation's projects.
 */

import { CalendarClock, ChevronDown } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ABSENCE_TYPE_LABELS } from "@/entities/absence";
import type { AbsenceRequest } from "@/entities/organisation";
import { useAbsenceRequests, useDecideAbsenceRequest } from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { formatDate, formatDateOnly } from "@/shared/lib";
import { Button, Chip } from "@/shared/ui";
import { CommentDialog } from "./CommentDialog";
import { memberLabel, projectLabel } from "./labels";
import { QueryBody, Section } from "./Section";
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
	// The decided ones, read only once asked for — a decider checking what
	// was already answered, or who answered it.
	const [showDecided, setShowDecided] = useState(false);
	const everything = useAbsenceRequests(organisationId, { enabled: showDecided });
	const decided = (everything.data ?? []).filter((r) => r.status !== "pending").slice(0, 20);

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
			<QueryBody
				query={requests}
				errorText="The requests could not be read."
				empty="Nothing waiting."
			>
				{(rows) => (
					<ul className={LIST}>
						{rows.map((request) => (
							<li key={request.id} className="py-2.5 text-[12.5px] space-y-1">
								<div className="flex items-center gap-2 flex-wrap">
									<span className="font-bold text-foreground">
										{memberLabel(request.memberName)}
									</span>
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
			</QueryBody>
			<div className="py-2">
				<button
					type="button"
					onClick={() => setShowDecided((o) => !o)}
					aria-expanded={showDecided}
					className="flex items-center gap-1.5 text-[12.5px] font-bold text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring rounded-full"
				>
					<ChevronDown
						className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${showDecided ? "" : "-rotate-90"}`}
						aria-hidden="true"
					/>
					{showDecided ? "Hide the decided ones" : "Recently decided"}
				</button>
				{showDecided &&
					(everything.error ? (
						<p className={`${LEAD} py-2`} role="alert">
							{describeError(everything.error, "The decided requests could not be read.")}
						</p>
					) : !everything.data ? (
						<p className={`${LEAD} py-2`}>Loading…</p>
					) : decided.length === 0 ? (
						<p className={`${LEAD} py-2`}>Nothing decided yet.</p>
					) : (
						<ul className={`${LIST} mt-1`}>
							{decided.map((request) => (
								<li key={request.id} className="py-2 text-[12.5px] space-y-0.5">
									<div className="flex items-center gap-2 flex-wrap">
										<span className="text-muted-foreground">{asked(request)}</span>
										<Chip tone={request.status === "approved" ? "ok" : "bad"}>
											{request.status}
										</Chip>
										{request.decidedByName && (
											<span className="text-muted-foreground">by {request.decidedByName}</span>
										)}
									</div>
									{request.comment && <p className="text-muted-foreground">“{request.comment}”</p>}
								</li>
							))}
						</ul>
					))}
			</div>
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
