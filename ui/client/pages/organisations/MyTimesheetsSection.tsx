/**
 * MyTimesheetsSection — the caller's own submitted months, and the control
 * to submit one: a month that has ended, on one of the organisation's
 * projects they are assigned to. For a member the API already answers with
 * their own sheets; a decider or viewer gets everyone's, so theirs are
 * picked out by the member row matching their address. Approval freezes
 * the month's figures; what the API refuses (409 MONTH_NOT_ENDED,
 * TIMESHEET_APPROVED) surfaces in its words.
 */

import { FileClock } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import type { OrgRole, Timesheet } from "@/entities/organisation";
import { useMembers, useSubmitTimesheet, useTimesheets } from "@/entities/organisation";
import { useProjects } from "@/entities/project";
import { useAuth } from "@/features/auth";
import { describeError } from "@/shared/api";
import { cn } from "@/shared/lib";
import { Button, Panel } from "@/shared/ui";
import { HEADING, HEADING_ICON, LABEL, LEAD, LIST, SELECT } from "./styles";
import { frozenText, STATUS_LABELS, sheetMonthTitle } from "./TimesheetsSection";

const STATUS_TONE: Record<Timesheet["status"], string> = {
	submitted: "text-accent-ink",
	approved: "text-success-ink",
	changes_requested: "text-muted-foreground",
	reopened: "text-muted-foreground",
};

/** The last `n` months that have ended, newest first, as YYYY-MM. */
export function endedMonths(n: number, today: Date = new Date()): string[] {
	const months: string[] = [];
	for (let i = 1; i <= n; i++) {
		const d = new Date(today.getFullYear(), today.getMonth() - i, 1, 12);
		months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
	}
	return months;
}

export function MyTimesheetsSection({
	organisationId,
	role,
}: {
	organisationId: string;
	role: OrgRole;
}) {
	const id = useId();
	const { user } = useAuth();
	const sheets = useTimesheets(organisationId);
	// A plain member may not list the members; their timesheets read is
	// already only their own.
	const members = useMembers(organisationId, { enabled: role !== "member" });
	const projects = useProjects();
	const submit = useSubmitTimesheet(organisationId);
	const months = endedMonths(6);
	const [month, setMonth] = useState(months[0]);
	const [projectId, setProjectId] = useState("");

	const mine = (projects.data ?? []).filter((p) => p.organisation?.id === organisationId);
	const myId =
		role === "member"
			? undefined
			: (members.data ?? []).find((m) => user?.email !== undefined && m.email === user.email)
					?.userId;
	const own =
		role === "member" ? (sheets.data ?? []) : (sheets.data ?? []).filter((s) => s.userId === myId);
	const rows = [...own].sort((a, b) => b.month.localeCompare(a.month));
	const projectName = (pid: string) => mine.find((p) => p.id === pid)?.name ?? "a project";

	const submitNow = () => {
		if (!projectId) return;
		submit.mutate(
			{ projectId, month },
			{
				onSuccess: () => toast.success(`Submitted ${sheetMonthTitle(`${month}-01`)}`),
				// 409 MONTH_NOT_ENDED / TIMESHEET_APPROVED: the API's words.
				onError: (err) => toast.error(describeError(err, "The month could not be submitted.")),
			},
		);
	};

	return (
		<section aria-label="Your timesheets" className="mb-8">
			<h2 className={HEADING}>
				<FileClock className={HEADING_ICON} />
				Your timesheets
			</h2>
			<p className={`${LEAD} -mt-1 mb-3`}>
				Submit a month once it has ended; approval freezes its figures and locks its days.
			</p>
			<Panel padding="px-5 py-3" className="space-y-3">
				{mine.length > 0 && (
					<div className="flex items-end gap-2 flex-wrap">
						<div>
							<label htmlFor={`${id}-month`} className={LABEL}>
								Month
							</label>
							<select
								id={`${id}-month`}
								value={month}
								onChange={(e) => setMonth(e.target.value)}
								className={SELECT}
							>
								{months.map((m) => (
									<option key={m} value={m}>
										{sheetMonthTitle(`${m}-01`)}
									</option>
								))}
							</select>
						</div>
						<div>
							<label htmlFor={`${id}-project`} className={LABEL}>
								Project
							</label>
							<select
								id={`${id}-project`}
								value={projectId}
								onChange={(e) => setProjectId(e.target.value)}
								className={SELECT}
							>
								<option value="">Choose…</option>
								{mine.map((p) => (
									<option key={p.id} value={p.id}>
										{p.name}
									</option>
								))}
							</select>
						</div>
						<Button
							type="button"
							size="sm"
							onClick={submitNow}
							disabled={!projectId || submit.isPending}
						>
							{submit.isPending ? "Submitting…" : "Submit"}
						</Button>
					</div>
				)}
				{sheets.error ? (
					<p className={LEAD} role="alert">
						{describeError(sheets.error, "Your timesheets could not be read.")}
					</p>
				) : !sheets.data ? (
					<p className={LEAD}>Loading…</p>
				) : rows.length === 0 ? (
					<p className={LEAD}>No months submitted yet.</p>
				) : (
					<ul className={LIST}>
						{rows.map((sheet) => (
							<li key={sheet.id} className="py-2.5 text-[12.5px] space-y-1">
								<div className="flex items-center gap-2 flex-wrap">
									<span className="font-bold text-foreground">{sheetMonthTitle(sheet.month)}</span>
									<span className="text-muted-foreground">{projectName(sheet.projectId)}</span>
									<span className={cn("font-bold", STATUS_TONE[sheet.status])}>
										{STATUS_LABELS[sheet.status]}
									</span>
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
		</section>
	);
}
