/**
 * AbsenceRequestsSection — the days off waiting on the caller's decision.
 * The note is addressed to the decider and never enters the record, which
 * the lead says. Either decision may carry a comment back; the API's own
 * words surface when a decision is refused (409 PERIOD_APPROVED while the
 * month is locked).
 */

import { CalendarClock } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import type { AbsenceRequest } from "@/entities/organisation";
import {
	useAbsenceRequests,
	useDecideAbsenceRequest,
	useMembers,
	useOrgProjects,
} from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { formatDateOnly } from "@/shared/lib";
import { Button, Dialog, Panel } from "@/shared/ui";
import { FIELD, HEADING, HEADING_ICON, LABEL, LEAD, LIST } from "./styles";

function DecisionDialog({
	request,
	approve,
	who,
	onClose,
	onDecide,
	busy,
}: {
	request: AbsenceRequest;
	approve: boolean;
	who: string;
	onClose: () => void;
	onDecide: (comment: string) => void;
	busy: boolean;
}) {
	const id = useId();
	const [comment, setComment] = useState("");
	return (
		<Dialog
			open
			onClose={() => !busy && onClose()}
			title={approve ? "Approve this day off?" : "Decline this day off?"}
			description={`${who} asked for ${formatDateOnly(request.date)} (${request.type}${request.halfDay ? ", half day" : ""}).`}
			contentClassName="sm:w-full sm:max-w-[380px]"
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					onDecide(comment.trim());
				}}
				noValidate
				className="space-y-3"
			>
				<div>
					<label htmlFor={`${id}-comment`} className={LABEL}>
						{approve ? "Comment (optional)" : "Comment (recommended)"}
					</label>
					<input
						id={`${id}-comment`}
						type="text"
						value={comment}
						onChange={(e) => setComment(e.target.value)}
						maxLength={500}
						autoFocus
						className={FIELD}
					/>
				</div>
				<div className="flex justify-end gap-2.5 pt-1">
					<Button type="button" variant="secondary" size="sm" onClick={onClose} disabled={busy}>
						Cancel
					</Button>
					<Button type="submit" size="sm" disabled={busy}>
						{busy ? "Sending…" : approve ? "Approve" : "Decline"}
					</Button>
				</div>
			</form>
		</Dialog>
	);
}

export function AbsenceRequestsSection({ organisationId }: { organisationId: string }) {
	const requests = useAbsenceRequests(organisationId, { pending: true });
	const members = useMembers(organisationId);
	const projects = useOrgProjects(organisationId);
	const decide = useDecideAbsenceRequest(organisationId);
	const [open, setOpen] = useState<{ request: AbsenceRequest; approve: boolean } | null>(null);

	const memberName = (userId: string) =>
		(members.data ?? []).find((m) => m.userId === userId)?.name ?? userId;
	const projectName = (projectId: string) =>
		(projects.data ?? []).find((p) => p.id === projectId)?.name ?? "a project";

	const decideNow = (request: AbsenceRequest, approve: boolean, comment: string) =>
		decide.mutate(
			{ requestId: request.id, approve, comment: comment || undefined },
			{
				onSuccess: () => {
					setOpen(null);
					toast.success(approve ? "Day off approved" : "Request declined");
				},
				// 409 PERIOD_APPROVED: the month is locked; the API's detail says so.
				onError: (err) => toast.error(describeError(err, "The request could not be decided.")),
			},
		);

	return (
		<section aria-label="Absence requests" className="mb-8">
			<h2 className={HEADING}>
				<CalendarClock className={HEADING_ICON} />
				Absence requests
			</h2>
			<p className={`${LEAD} -mt-1 mb-3`}>
				The note is addressed to you — the record never shows it.
			</p>
			<Panel padding="px-5 py-1">
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
									<span className="font-bold text-foreground">{memberName(request.userId)}</span>
									<span className="text-muted-foreground">
										{projectName(request.projectId)} · {formatDateOnly(request.date)} ·{" "}
										{request.type}
										{request.halfDay && " · half day"}
									</span>
									<span className="ml-auto flex items-center gap-2">
										<Button
											type="button"
											size="sm"
											className="h-7 px-2.5 text-xs"
											onClick={() => setOpen({ request, approve: true })}
											disabled={decide.isPending}
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
			</Panel>
			{open && (
				<DecisionDialog
					key={`${open.request.id}-${open.approve}`}
					request={open.request}
					approve={open.approve}
					who={memberName(open.request.userId)}
					onClose={() => setOpen(null)}
					onDecide={(comment) => decideNow(open.request, open.approve, comment)}
					busy={decide.isPending}
				/>
			)}
		</section>
	);
}
