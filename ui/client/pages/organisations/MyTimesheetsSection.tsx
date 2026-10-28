/**
 * MyTimesheetsSection — the caller's own submitted months, and the control
 * to submit one: a month that has ended, on one of the organisation's
 * projects they are assigned to. Which months have ended is the
 * organisation's call, in its timezone (409 MONTH_NOT_ENDED otherwise), so
 * the list is computed from `organisationToday`, and months already
 * submitted or approved are not offered again. A sheet sent back carries
 * its own Resubmit. For a member the API already answers with their own
 * sheets; a decider or viewer gets everyone's, so theirs are picked out by
 * `userId`, the membership's own.
 */

import { FileClock } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import {
	endedMonths,
	frozenText,
	organisationToday,
	sheetMonthTitle,
	TIMESHEET_STATUS_LABELS,
	TIMESHEET_STATUS_TONE,
	useSubmitTimesheet,
	useTimesheets,
} from "@/entities/organisation";
import { useProjects } from "@/entities/project";
import { describeError } from "@/shared/api";
import { Button, Chip } from "@/shared/ui";
import { projectLabel } from "./labels";
import { Section } from "./Section";
import { LABEL, LEAD, LIST, SELECT } from "./styles";

export function MyTimesheetsSection({
	organisationId,
	userId,
	timezone,
}: {
	organisationId: string;
	/** The caller's own, off their membership. */
	userId: string;
	/** The organisation's: it decides when a month has ended. */
	timezone: string;
}) {
	const id = useId();
	const sheets = useTimesheets(organisationId);
	const projects = useProjects();
	const submit = useSubmitTimesheet(organisationId);
	const [month, setMonth] = useState("");
	const [projectId, setProjectId] = useState("");

	const mine = (projects.data ?? []).filter((p) => p.organisation?.id === organisationId);
	const own = (sheets.data ?? []).filter((s) => s.userId === userId);
	const rows = [...own].sort((a, b) => b.month.localeCompare(a.month));

	// A month already submitted or approved on the chosen project is not
	// offered: sending it again is a 409 the dropdown can see coming. One
	// sent back or reopened is — that is what resubmitting is.
	const settledOn = (pid: string) =>
		new Set(
			own
				.filter((s) => s.projectId === pid && (s.status === "submitted" || s.status === "approved"))
				.map((s) => s.month),
		);
	const ended = endedMonths(organisationToday(timezone), 6);
	const settled = projectId ? settledOn(projectId) : new Set<string>();
	const openMonths = ended.filter((m) => !settled.has(m));
	const chosen = openMonths.includes(month) ? month : (openMonths[0] ?? "");

	const submitNow = (pid: string, m: string) => {
		if (!pid || !m) return;
		submit.mutate(
			{ projectId: pid, month: m },
			{
				onSuccess: () => toast.success(`Submitted ${sheetMonthTitle(m)}`),
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
			{projects.data && mine.length === 0 ? (
				<p className={LEAD}>
					You're not on any of this organisation's projects, so there is no month to submit.
				</p>
			) : mine.length > 0 ? (
				<div className="flex items-end gap-2 flex-wrap">
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
					<div>
						<label htmlFor={`${id}-month`} className={LABEL}>
							Month
						</label>
						<select
							id={`${id}-month`}
							value={chosen}
							onChange={(e) => setMonth(e.target.value)}
							disabled={openMonths.length === 0}
							className={SELECT}
						>
							{openMonths.length === 0 ? (
								<option value="">Every recent month is in</option>
							) : (
								openMonths.map((m) => (
									<option key={m} value={m}>
										{sheetMonthTitle(m)}
									</option>
								))
							)}
						</select>
					</div>
					<Button
						type="button"
						size="sm"
						onClick={() => submitNow(projectId, chosen)}
						disabled={!projectId || !chosen || submit.isPending}
					>
						{submit.isPending ? "Submitting…" : "Submit"}
					</Button>
				</div>
			) : null}
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
								<Chip tone={TIMESHEET_STATUS_TONE[sheet.status]}>
									{TIMESHEET_STATUS_LABELS[sheet.status]}
								</Chip>
								{(sheet.status === "changes_requested" || sheet.status === "reopened") && (
									<Button
										type="button"
										variant="secondary"
										size="sm"
										className="ml-auto h-7 px-2.5 text-xs"
										onClick={() => submitNow(sheet.projectId, sheet.month)}
										disabled={submit.isPending}
										aria-label={`Resubmit ${sheetMonthTitle(sheet.month)} on ${projectLabel(sheet.projectName)}`}
									>
										Resubmit
									</Button>
								)}
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
