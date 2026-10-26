/**
 * MyTimesheetsSection — the caller's own submitted months, and the control
 * to submit one: a month that has ended, on one of the organisation's
 * projects they are assigned to. For a member the API already answers with
 * their own sheets; a decider or viewer gets everyone's, so theirs are
 * picked out by `userId`, the membership's own — never by the address they
 * joined under, which an account that has since changed its email, or came
 * in through single sign-on, no longer matches. Approval freezes the
 * month's figures; what the API refuses (409 MONTH_NOT_ENDED,
 * TIMESHEET_APPROVED) surfaces in its words.
 */

import { FileClock } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import type { Timesheet } from "@/entities/organisation";
import { useSubmitTimesheet, useTimesheets } from "@/entities/organisation";
import { useProjects } from "@/entities/project";
import { describeError } from "@/shared/api";
import { cn } from "@/shared/lib";
import { Button } from "@/shared/ui";
import { projectLabel } from "./labels";
import { Section } from "./Section";
import { LABEL, LEAD, LIST, SELECT } from "./styles";
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
	userId,
}: {
	organisationId: string;
	/** The caller's own, off their membership. */
	userId: string;
}) {
	const id = useId();
	const sheets = useTimesheets(organisationId);
	const projects = useProjects();
	const submit = useSubmitTimesheet(organisationId);
	const months = endedMonths(6);
	const [month, setMonth] = useState(months[0]);
	const [projectId, setProjectId] = useState("");

	const mine = (projects.data ?? []).filter((p) => p.organisation?.id === organisationId);
	const own = (sheets.data ?? []).filter((s) => s.userId === userId);
	const rows = [...own].sort((a, b) => b.month.localeCompare(a.month));

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
		<Section
			label="Your timesheets"
			icon={FileClock}
			lead="Submit a month once it has ended; approval freezes its figures and locks its days."
			bodyClassName="px-5 py-3 space-y-3"
		>
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
								<span className="text-muted-foreground">{projectLabel(sheet.projectName)}</span>
								<span className={cn("font-bold", STATUS_TONE[sheet.status])}>
									{STATUS_LABELS[sheet.status]}
								</span>
							</div>
							{sheet.status === "approved" && sheet.frozen && (
								<p className="text-foreground font-medium font-mono">{frozenText(sheet.frozen)}</p>
							)}
							{sheet.comment && <p className="text-muted-foreground">“{sheet.comment}”</p>}
						</li>
					))}
				</ul>
			)}
		</Section>
	);
}
