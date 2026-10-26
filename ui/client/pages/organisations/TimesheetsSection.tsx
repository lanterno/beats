/**
 * TimesheetsSection — every submitted month for the people who decide them
 * (and for a viewer, read-only), grouped by whose move it is: a submitted
 * sheet waits on the decider; one sent back or reopened is with the member;
 * an approved one is settled. Approval freezes the month's figures and
 * locks its days; "Ask for changes" requires the words the member will act
 * on; reopening says whose month it is and takes the frozen figures with
 * it. Each row links the month in the record — the evidence — and a
 * decider's own month says so, since the API lets them approve it.
 *
 * Contract… and Enter time… sit on the row for deciders: a manager may do
 * both within their scope but cannot reach the admin-only Projects tab, so
 * the row is their one entry point.
 */

import { ClipboardCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import type { OrgRole, Timesheet } from "@/entities/organisation";
import {
	decides,
	frozenText,
	sheetMonthTitle,
	TIMESHEET_STATUS_LABELS,
	TIMESHEET_STATUS_TONE,
	useDecideTimesheet,
	useReopenTimesheet,
	useTimesheets,
} from "@/entities/organisation";
import { describeError } from "@/shared/api";
import { formatDate } from "@/shared/lib";
import { Button, Chip } from "@/shared/ui";
import { CommentDialog } from "./CommentDialog";
import { EnterTimeDialog } from "./EnterTimeDialog";
import { memberLabel, projectLabel } from "./labels";
import { ManagedContractDialog } from "./ManagedContractDialog";
import { RecordMonthLink } from "./RecordMonthLink";
import { Section } from "./Section";
import { LEAD, LINKISH, LIST } from "./styles";

type Action = { sheet: Timesheet; kind: "approve" | "changes" | "reopen" };
type MemberAct = { sheet: Timesheet; kind: "contract" | "time" };

/** Whose move a sheet waits on, in the order the list shows. */
const GROUPS = [
	{ key: "deciding", title: "Waiting on you", of: (s: Timesheet) => s.status === "submitted" },
	{
		key: "member",
		title: "With the member",
		of: (s: Timesheet) => s.status === "changes_requested" || s.status === "reopened",
	},
	{ key: "approved", title: "Approved", of: (s: Timesheet) => s.status === "approved" },
] as const;

/** "submitted Oct 1", or "submitted again Oct 12" when it came back. */
function submittedWords(sheet: Timesheet): string {
	const times = sheet.history.filter((h) => h.action === "submitted").length;
	return `${times > 1 ? "submitted again" : "submitted"} ${formatDate(sheet.submittedAt)}`;
}

export function TimesheetsSection({
	organisationId,
	role,
	userId,
}: {
	organisationId: string;
	role: OrgRole;
	/** The caller's own, so their own month says so beside Approve. */
	userId: string;
}) {
	const sheets = useTimesheets(organisationId);
	const decide = useDecideTimesheet(organisationId);
	const reopen = useReopenTimesheet(organisationId);
	const [action, setAction] = useState<Action | null>(null);
	const [act, setAct] = useState<MemberAct | null>(null);
	const mayDecide = decides(role);
	const busy = decide.isPending || reopen.isPending;

	const send = async (a: Action, comment: string) => {
		if (a.kind === "reopen") {
			await reopen.mutateAsync({ sheetId: a.sheet.id, reason: comment });
		} else {
			await decide.mutateAsync({
				sheetId: a.sheet.id,
				approve: a.kind === "approve",
				comment: comment || undefined,
			});
		}
		setAction(null);
		toast.success(
			a.kind === "approve"
				? "Month approved"
				: a.kind === "changes"
					? "Changes asked for"
					: "Month reopened",
		);
	};

	const rows = [...(sheets.data ?? [])].sort((a, b) => b.month.localeCompare(a.month));
	const who = (sheet: Timesheet) =>
		`${memberLabel(sheet.memberName)} · ${projectLabel(sheet.projectName)} · ${sheetMonthTitle(sheet.month)}`;

	const sheetRow = (sheet: Timesheet) => (
		<li key={sheet.id} className="py-2.5 text-[12.5px] space-y-1">
			<div className="flex items-center gap-2 flex-wrap">
				<span className="font-bold text-foreground">{memberLabel(sheet.memberName)}</span>
				{sheet.userId === userId && <span className="text-muted-foreground">(your month)</span>}
				<span className="text-muted-foreground">
					{projectLabel(sheet.projectName)} ·{" "}
					<RecordMonthLink organisationId={organisationId} month={sheet.month}>
						{sheetMonthTitle(sheet.month)}
					</RecordMonthLink>{" "}
					· {submittedWords(sheet)}
				</span>
				<Chip tone={TIMESHEET_STATUS_TONE[sheet.status]}>
					{TIMESHEET_STATUS_LABELS[sheet.status]}
				</Chip>
				{mayDecide && (
					<span className="ml-auto flex items-center gap-2">
						{sheet.status === "approved" ? (
							<button
								type="button"
								onClick={() => setAction({ sheet, kind: "reopen" })}
								disabled={busy}
								aria-label={`Reopen ${who(sheet)}`}
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
									aria-label={`Approve ${who(sheet)}`}
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
									aria-label={`Ask for changes on ${who(sheet)}`}
								>
									Ask for changes
								</Button>
							</>
						)}
						<button
							type="button"
							onClick={() => setAct({ sheet, kind: "contract" })}
							aria-label={`Contract of ${memberLabel(sheet.memberName)} on ${projectLabel(sheet.projectName)}`}
							className={LINKISH}
						>
							Contract…
						</button>
						<button
							type="button"
							onClick={() => setAct({ sheet, kind: "time" })}
							aria-label={`Enter time for ${memberLabel(sheet.memberName)} on ${projectLabel(sheet.projectName)}`}
							className={LINKISH}
						>
							Enter time…
						</button>
					</span>
				)}
			</div>
			{sheet.status === "approved" && sheet.frozen && (
				<p className="text-foreground font-medium font-mono">{frozenText(sheet.frozen)}</p>
			)}
			{sheet.comment && <p className="text-muted-foreground">“{sheet.comment}”</p>}
		</li>
	);

	return (
		<Section
			label="Timesheets"
			icon={ClipboardCheck}
			lead="Approval freezes a month's figures and locks its days until it is reopened."
		>
			{sheets.error ? (
				<p className={`${LEAD} py-3`} role="alert">
					{describeError(sheets.error, "The timesheets could not be read.")}
				</p>
			) : !sheets.data ? (
				<p className={`${LEAD} py-3`}>Loading…</p>
			) : rows.length === 0 ? (
				<p className={`${LEAD} py-3`}>No months submitted yet.</p>
			) : (
				GROUPS.map(({ key, title, of }) => {
					const inGroup = rows.filter(of);
					if (inGroup.length === 0) return null;
					return (
						<div key={key} className="py-1.5">
							<h3 className="font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground pt-2">
								{title}
							</h3>
							<ul className={LIST}>{inGroup.map(sheetRow)}</ul>
						</div>
					);
				})
			)}
			{action?.kind === "approve" && (
				<CommentDialog
					key={action.sheet.id}
					title="Approve this month?"
					context={`${who(action.sheet)} — its figures freeze as they stand and every day in it locks.`}
					hint={
						<p className={LEAD}>
							{submittedWords(action.sheet)} ·{" "}
							<RecordMonthLink organisationId={organisationId} month={action.sheet.month}>
								See the month in the record
							</RecordMonthLink>
						</p>
					}
					commentLabel="Comment (optional)"
					confirmLabel="Approve"
					busyLabel="Approving…"
					onClose={() => setAction(null)}
					onSend={(comment) => send(action, comment)}
				/>
			)}
			{action?.kind === "changes" && (
				<CommentDialog
					key={action.sheet.id}
					title="Ask for changes?"
					context={`${who(action.sheet)} goes back to ${memberLabel(action.sheet.memberName)} with your words.`}
					commentLabel="What should change"
					commentRequired
					confirmLabel="Ask for changes"
					busyLabel="Sending…"
					onClose={() => setAction(null)}
					onSend={(comment) => send(action, comment)}
				/>
			)}
			{action?.kind === "reopen" && (
				<CommentDialog
					key={action.sheet.id}
					title="Reopen this month?"
					context={`${who(action.sheet)} — the lock lifts, the frozen figures go with it, and the reason is recorded.`}
					commentLabel="Why it reopens"
					commentRequired
					confirmLabel="Reopen"
					busyLabel="Reopening…"
					danger
					onClose={() => setAction(null)}
					onSend={(comment) => send(action, comment)}
				/>
			)}
			{act?.kind === "contract" && (
				<ManagedContractDialog
					key={`${act.sheet.projectId}-${act.sheet.userId}`}
					organisationId={organisationId}
					projectId={act.sheet.projectId}
					projectName={projectLabel(act.sheet.projectName)}
					userId={act.sheet.userId}
					memberName={memberLabel(act.sheet.memberName)}
					onClose={() => setAct(null)}
				/>
			)}
			{act?.kind === "time" && (
				<EnterTimeDialog
					key={`${act.sheet.projectId}-${act.sheet.userId}`}
					organisationId={organisationId}
					projectId={act.sheet.projectId}
					projectName={projectLabel(act.sheet.projectName)}
					userId={act.sheet.userId}
					memberName={memberLabel(act.sheet.memberName)}
					onClose={() => setAct(null)}
				/>
			)}
		</Section>
	);
}
