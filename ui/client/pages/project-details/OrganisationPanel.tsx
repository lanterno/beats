/**
 * OrganisationPanel — the rail's Organisation (docs/organisations.md). On
 * an organisation's project: whose it is, since when the hours on it are
 * theirs, and where to see what they see. On a personal project of a
 * member: the offer to connect it, from a day they choose — a dialog of
 * its own on the page, not a step buried in the settings drawer. Nothing
 * for a person in no organisation, or on a project billed to a client,
 * which stays personal.
 */

import { Building2 } from "lucide-react";
import { useId, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import type { Timesheet, TimesheetStatus } from "@/entities/organisation";
import {
	ConnectProjectDialog,
	describeShareFrom,
	OrganisationMark,
	useMemberships,
	useSubmitTimesheet,
	useTimesheets,
} from "@/entities/organisation";
import type { ProjectWithDuration } from "@/entities/project";
import { describeError } from "@/shared/api";
import { parseIsoDate } from "@/shared/lib";
import { Button, Panel } from "@/shared/ui";
import { LABEL, LINKISH, SELECT_PILL } from "./styles";

export interface OrganisationPanelProps {
	project: ProjectWithDuration;
	todayIso: string;
	/** Billed to a client: the API refuses to connect it, so nothing is offered. */
	billed?: boolean;
}

/** "September 2026" from a sheet month's "2026-09-01". */
function monthLabel(month: string): string {
	const d = parseIsoDate(month);
	return d ? d.toLocaleDateString("en-US", { month: "long", year: "numeric" }) : month;
}

/** "approved · 42.5 h" with what approval froze, else the status in words. */
function sheetWords(sheet: Timesheet): string {
	const words: Record<TimesheetStatus, string> = {
		submitted: "submitted",
		approved: "approved",
		changes_requested: "changes requested",
		reopened: "reopened",
	};
	if (sheet.status === "approved" && sheet.frozen) {
		return `approved · ${Math.round(sheet.frozen.worked * 10) / 10} h`;
	}
	return words[sheet.status];
}

/** The last `n` ended months before the month `todayIso` sits in, newest first, as "YYYY-MM-01". */
function endedMonths(todayIso: string, n: number): string[] {
	const year = Number(todayIso.slice(0, 4));
	const month = Number(todayIso.slice(5, 7));
	return Array.from({ length: n }, (_, i) => {
		const d = new Date(year, month - 1 - (i + 1), 1, 12);
		return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
	});
}

/**
 * My timesheets on this project — the API answers a member only their own —
 * and a submit for an ended month without a submitted or approved sheet.
 */
function TimesheetsBlock({
	organisationId,
	projectId,
	todayIso,
}: {
	organisationId: string;
	projectId: string;
	todayIso: string;
}) {
	const id = useId();
	const { data: timesheets } = useTimesheets(organisationId);
	const submit = useSubmitTimesheet(organisationId);
	const mine = (timesheets ?? [])
		.filter((t) => t.projectId === projectId)
		.sort((a, b) => b.month.localeCompare(a.month));
	const settled = new Set(
		mine.filter((t) => t.status === "submitted" || t.status === "approved").map((t) => t.month),
	);
	const open = endedMonths(todayIso, 6).filter((m) => !settled.has(m));
	const [month, setMonth] = useState("");
	const chosen = month || open[0] || "";

	return (
		<div className="mt-3 pt-2.5 border-t border-border">
			<h4 className={LABEL}>Timesheets</h4>
			<p className="mt-1 text-xs text-muted-foreground font-medium leading-normal">
				Approval freezes the month and locks its days; a decider can reopen it.
			</p>
			{mine.length > 0 && (
				<ul className="mt-1.5 flex flex-col" aria-label="Timesheets">
					{mine.map((sheet) => (
						<li
							key={sheet.id}
							className="py-[5px] border-t border-border first:border-t-0 text-[12.5px] font-medium text-foreground"
						>
							{monthLabel(sheet.month)} — {sheetWords(sheet)}
						</li>
					))}
				</ul>
			)}
			{open.length > 0 && (
				<div className="mt-2 flex items-center gap-2">
					<label htmlFor={`${id}-month`} className="sr-only">
						Month to submit
					</label>
					<select
						id={`${id}-month`}
						value={chosen}
						onChange={(e) => setMonth(e.target.value)}
						className={SELECT_PILL}
					>
						{open.map((m) => (
							<option key={m} value={m}>
								{monthLabel(m)}
							</option>
						))}
					</select>
					<Button
						type="button"
						variant="secondary"
						size="sm"
						disabled={submit.isPending || !chosen}
						onClick={() =>
							submit.mutate(
								{ projectId, month: chosen },
								{
									onSuccess: () => toast.success("Timesheet submitted"),
									onError: (err) =>
										toast.error(describeError(err, "Failed to submit the timesheet")),
								},
							)
						}
					>
						Submit
					</Button>
				</div>
			)}
		</div>
	);
}

export function OrganisationPanel({ project, todayIso, billed = false }: OrganisationPanelProps) {
	const { data: memberships } = useMemberships();
	const [connecting, setConnecting] = useState(false);
	const active = (memberships ?? []).filter((m) => m.leftAt === undefined);
	const organisation = project.organisation;

	if (organisation) {
		return (
			<Panel role="region" aria-label="Organisation" padding="px-6 py-5">
				<p className={LABEL}>Organisation</p>
				<div className="mt-2 flex items-center gap-2">
					<OrganisationMark name={organisation.name} logoUrl={organisation.logoUrl} size="md" />
				</div>
				<p className="mt-1.5 text-[12.5px] font-medium text-muted-foreground leading-normal">
					{organisation.name} owns this project and sees your hours on it{" "}
					{describeShareFrom(organisation.sharedFrom)}.{" "}
					{organisation.contractManaged
						? `Your goal and local repo paths stay yours; ${organisation.name} manages the contract and your days off.`
						: "Your goal, local repo paths and contract stay yours."}
				</p>
				<div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1">
					<Link to={`/organisations/${organisation.id}/visible`} className={LINKISH}>
						What {organisation.name} can see
					</Link>
					<Link to={`/organisations/${organisation.id}`} className={LINKISH}>
						Open {organisation.name}
					</Link>
				</div>
				<TimesheetsBlock
					organisationId={organisation.id}
					projectId={project.id}
					todayIso={todayIso}
				/>
			</Panel>
		);
	}

	if (active.length === 0 || billed || project.archived) return null;

	const only = active.length === 1 ? active[0].organisation.name : null;
	return (
		<Panel role="region" aria-label="Organisation" padding="px-6 py-5">
			<p className={LABEL}>Organisation</p>
			<p className="mt-2 text-[12.5px] font-medium text-muted-foreground leading-normal">
				Yours alone. Connecting it makes its hours part of an organisation's working-time record,
				from a day you choose.
			</p>
			<Button
				type="button"
				variant="secondary"
				size="sm"
				className="mt-3"
				onClick={() => setConnecting(true)}
			>
				<Building2 aria-hidden="true" />
				{only ? `Connect to ${only}…` : "Connect to an organisation…"}
			</Button>
			{connecting && (
				<ConnectProjectDialog
					project={{ id: project.id, name: project.name }}
					memberships={active}
					todayIso={todayIso}
					onConnected={() => setConnecting(false)}
					onClose={() => setConnecting(false)}
				/>
			)}
		</Panel>
	);
}
