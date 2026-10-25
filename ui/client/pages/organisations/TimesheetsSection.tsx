/**
 * TimesheetsSection — every submitted month, newest first, for the people
 * who decide them (and for a viewer, read-only). Approval freezes the
 * month's figures and locks its days; reopening lifts the lock, takes the
 * frozen figures with it, and re-approval freezes afresh. A decision the
 * month refuses (409, a running timer in it) answers in the API's words.
 */

import { ClipboardCheck } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import type { OrgRole, Timesheet } from "@/entities/organisation";
import {
	decides,
	useDecideTimesheet,
	useMembers,
	useOrgProjects,
	useReopenTimesheet,
	useTimesheets,
} from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { cn, hoursText } from "@/shared/lib";
import { Button, Dialog, Panel } from "@/shared/ui";
import { FIELD, HEADING, HEADING_ICON, LABEL, LEAD, LINKISH, LIST } from "./styles";

export const STATUS_LABELS: Record<Timesheet["status"], string> = {
	submitted: "Submitted",
	approved: "Approved",
	changes_requested: "Changes requested",
	reopened: "Reopened",
};

const STATUS_TONE: Record<Timesheet["status"], string> = {
	submitted: "text-accent-ink",
	approved: "text-success-ink",
	changes_requested: "text-muted-foreground",
	reopened: "text-muted-foreground",
};

/** "September 2026" from the sheet's YYYY-MM-01. */
export function sheetMonthTitle(month: string): string {
	const date = new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1, 1, 12);
	return date.toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

/** "42.5 h worked · 160 h expected · balance −12.3 h at the close". */
export function frozenText(frozen: NonNullable<Timesheet["frozen"]>): string {
	const parts = [`${hoursText(frozen.worked)} worked`];
	if (frozen.expected !== null) parts.push(`${hoursText(frozen.expected)} expected`);
	if (frozen.balanceEnd !== null) {
		const b = frozen.balanceEnd;
		const signed = b < 0 ? `−${hoursText(-b)}` : `+${hoursText(b)}`;
		parts.push(`balance ${signed} at the close`);
	}
	return parts.join(" · ");
}

type Action = { sheet: Timesheet; kind: "approve" | "changes" | "reopen" };

function ActionDialog({
	action,
	title,
	onClose,
	onSend,
	busy,
}: {
	action: Action;
	title: string;
	onClose: () => void;
	onSend: (comment: string) => void;
	busy: boolean;
}) {
	const id = useId();
	const [comment, setComment] = useState("");
	const reopen = action.kind === "reopen";
	const [error, setError] = useState("");
	return (
		<Dialog
			open
			onClose={() => !busy && onClose()}
			title={
				action.kind === "approve"
					? "Approve this month?"
					: action.kind === "changes"
						? "Ask for changes?"
						: "Reopen this month?"
			}
			description={
				reopen
					? "Reopening lifts the month's lock; the frozen figures go with it and re-approval freezes afresh."
					: title
			}
			contentClassName="sm:w-full sm:max-w-[380px]"
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					const trimmed = comment.trim();
					if (reopen && !trimmed) {
						setError("Reopening needs a reason.");
						return;
					}
					onSend(trimmed);
				}}
				noValidate
				className="space-y-3"
			>
				<div>
					<label htmlFor={`${id}-comment`} className={LABEL}>
						{reopen
							? "Reason"
							: action.kind === "approve"
								? "Comment (optional)"
								: "What should change"}
					</label>
					<input
						id={`${id}-comment`}
						type="text"
						value={comment}
						onChange={(e) => setComment(e.target.value)}
						maxLength={500}
						autoFocus
						aria-invalid={error ? true : undefined}
						className={FIELD}
					/>
					{error && <p className="mt-1 text-xs text-destructive-ink">{error}</p>}
				</div>
				<div className="flex justify-end gap-2.5 pt-1">
					<Button type="button" variant="secondary" size="sm" onClick={onClose} disabled={busy}>
						Cancel
					</Button>
					<Button type="submit" size="sm" disabled={busy}>
						{busy
							? "Sending…"
							: action.kind === "approve"
								? "Approve"
								: action.kind === "changes"
									? "Ask for changes"
									: "Reopen"}
					</Button>
				</div>
			</form>
		</Dialog>
	);
}

export function TimesheetsSection({
	organisationId,
	role,
}: {
	organisationId: string;
	role: OrgRole;
}) {
	const sheets = useTimesheets(organisationId);
	const members = useMembers(organisationId);
	const projects = useOrgProjects(organisationId);
	const decide = useDecideTimesheet(organisationId);
	const reopen = useReopenTimesheet(organisationId);
	const [action, setAction] = useState<Action | null>(null);
	const mayDecide = decides(role);
	const busy = decide.isPending || reopen.isPending;

	const memberName = (userId: string) =>
		(members.data ?? []).find((m) => m.userId === userId)?.name ?? userId;
	const projectName = (projectId: string) =>
		(projects.data ?? []).find((p) => p.id === projectId)?.name ?? "a project";

	const send = (act: Action, comment: string) => {
		const done = {
			onSuccess: () => {
				setAction(null);
				toast.success(
					act.kind === "approve"
						? "Month approved"
						: act.kind === "changes"
							? "Changes asked for"
							: "Month reopened",
				);
			},
			// A 409 (PERIOD_APPROVED, a timer still running in the month) answers
			// in the API's words.
			onError: (err: unknown) =>
				toast.error(describeError(err, "The timesheet could not be decided.")),
		};
		if (act.kind === "reopen") reopen.mutate({ sheetId: act.sheet.id, reason: comment }, done);
		else
			decide.mutate(
				{ sheetId: act.sheet.id, approve: act.kind === "approve", comment: comment || undefined },
				done,
			);
	};

	const rows = [...(sheets.data ?? [])].sort((a, b) => b.month.localeCompare(a.month));

	return (
		<section aria-label="Timesheets" className="mb-8">
			<h2 className={HEADING}>
				<ClipboardCheck className={HEADING_ICON} />
				Timesheets
			</h2>
			<p className={`${LEAD} -mt-1 mb-3`}>
				Approval freezes a month's figures and locks its days until it is reopened.
			</p>
			<Panel padding="px-5 py-1">
				{sheets.error ? (
					<p className={`${LEAD} py-3`} role="alert">
						{describeError(sheets.error, "The timesheets could not be read.")}
					</p>
				) : !sheets.data ? (
					<p className={`${LEAD} py-3`}>Loading…</p>
				) : rows.length === 0 ? (
					<p className={`${LEAD} py-3`}>No months submitted yet.</p>
				) : (
					<ul className={LIST}>
						{rows.map((sheet) => (
							<li key={sheet.id} className="py-2.5 text-[12.5px] space-y-1">
								<div className="flex items-center gap-2 flex-wrap">
									<span className="font-bold text-foreground">{memberName(sheet.userId)}</span>
									<span className="text-muted-foreground">
										{projectName(sheet.projectId)} · {sheetMonthTitle(sheet.month)}
									</span>
									<span className={cn("font-bold", STATUS_TONE[sheet.status])}>
										{STATUS_LABELS[sheet.status]}
									</span>
									{mayDecide && (
										<span className="ml-auto flex items-center gap-2">
											{sheet.status === "approved" ? (
												<button
													type="button"
													onClick={() => setAction({ sheet, kind: "reopen" })}
													disabled={busy}
													className={LINKISH}
												>
													Reopen…
												</button>
											) : (
												<>
													<Button
														type="button"
														size="sm"
														className="h-7 px-2.5 text-xs"
														onClick={() => setAction({ sheet, kind: "approve" })}
														disabled={busy}
													>
														Approve
													</Button>
													<Button
														type="button"
														variant="secondary"
														size="sm"
														className="h-7 px-2.5 text-xs"
														onClick={() => setAction({ sheet, kind: "changes" })}
														disabled={busy}
													>
														Ask for changes
													</Button>
												</>
											)}
										</span>
									)}
								</div>
								{sheet.status === "approved" && sheet.frozen && (
									<p className="text-foreground font-medium font-mono">
										{frozenText(sheet.frozen)}
									</p>
								)}
								{sheet.comment && <p className="text-muted-foreground">“{sheet.comment}”</p>}
							</li>
						))}
					</ul>
				)}
			</Panel>
			{action && (
				<ActionDialog
					key={`${action.sheet.id}-${action.kind}`}
					action={action}
					title={`${memberName(action.sheet.userId)} · ${projectName(action.sheet.projectId)} · ${sheetMonthTitle(action.sheet.month)}.`}
					onClose={() => setAction(null)}
					onSend={(comment) => send(action, comment)}
					busy={busy}
				/>
			)}
		</section>
	);
}
