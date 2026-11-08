/**
 * The organisations the platform runs for: rosters, states and the audit of
 * acts — settings and counts, never a figure from anyone's record. The
 * operator acts here only for an organisation with no owner, and only when
 * asked — each act refused server-side the moment an owner exists.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { get } from "@/shared/api/client";
import type { OrgAuditRow, OrganisationDetail, OrganisationSummary } from "@/shared/api/schema";
import { counted, dayOf, minuteOf } from "@/shared/lib/format";
import {
	Chip,
	day,
	Empty,
	Facts,
	Failed,
	figure,
	Id,
	Loading,
	Page,
	Panel,
	Table,
	TextField,
} from "@/shared/ui";
import { CommandForm } from "@/shared/ui/CommandForm";

function roles(byRole: Record<string, number> | undefined): string {
	const entries = Object.entries(byRole ?? {});
	if (entries.length === 0) return "Nobody";
	return entries.map(([role, n]) => counted(n, role, `${role}s`)).join(", ");
}

function State({ organisation: o }: { organisation: OrganisationSummary }) {
	if (o.closes_on) return <Chip>Closing {o.closes_on}</Chip>;
	if (o.owners === 0) return <Chip tone="owed">No owner</Chip>;
	if (o.all_owners_suspended) return <Chip tone="owed">Every owner suspended</Chip>;
	return <Chip tone="good">Open</Chip>;
}

export function Organisations() {
	const { data, error, refetch } = useQuery({
		queryKey: ["organisations"],
		queryFn: () => get<OrganisationSummary[]>("/api/operator/organisations"),
	});
	if (error) return <Failed error={error} onRetry={() => refetch()} />;
	if (!data) return <Loading />;

	const ownerless = data.filter((o) => o.owners === 0).length;

	return (
		<Page
			title="Organisations"
			lead={
				ownerless > 0
					? `${counted(data.length, "organisation", "organisations")} on the platform, and ${counted(ownerless, "has", "have")} no owner.`
					: `${counted(data.length, "organisation", "organisations")} on the platform, each with an owner.`
			}
		>
			<Panel raised>
				<div className="pt-3">
					<Table
						head={["Name", day("Created"), "Members", figure("Assignments"), "Retention", "State"]}
						rows={data.map((o) => [
							<Link key={o.id} to={`/organisations/${o.id}`} className="link">
								{o.name}
							</Link>,
							dayOf(o.created_at),
							roles(o.members_by_role),
							o.active_assignments,
							o.retention_years ? `${o.retention_years} years` : "Default",
							<State key="state" organisation={o} />,
						])}
						empty={
							<Empty title="No organisations yet.">
								One appears here as soon as somebody creates it.
							</Empty>
						}
					/>
				</div>
			</Panel>
		</Page>
	);
}

export function Organisation() {
	const { id } = useParams();
	const { data, error, refetch } = useQuery({
		queryKey: ["organisation", id],
		queryFn: () => get<OrganisationDetail>(`/api/operator/organisations/${id}`),
	});
	const audit = useQuery({
		queryKey: ["organisation-audit", id],
		queryFn: () => get<OrgAuditRow[]>(`/api/operator/organisations/${id}/audit`),
	});
	if (error) return <Failed error={error} onRetry={() => refetch()} />;
	if (!data) return <Loading />;
	const s = data.summary;

	return (
		<Page
			title={s.name}
			back={{ to: "/organisations", label: "All organisations" }}
			lead={
				s.closes_on
					? `Closing on ${s.closes_on}.`
					: s.owners === 0
						? "No owner is left."
						: s.all_owners_suspended
							? "Every owner is suspended."
							: `Open, with ${counted(s.owners, "owner", "owners")}.`
			}
			aside={
				<div className="mt-2.5 rounded-full bg-panel-solid">
					<State organisation={s} />
				</div>
			}
		>
			<Panel
				title="The organisation"
				note="Settings and counts, never a figure from anyone's record."
			>
				<Facts
					items={[
						["Created", dayOf(s.created_at)],
						["Members", roles(s.members_by_role)],
						["Owners", s.owners],
						["Active assignments", s.active_assignments],
						["Projects", `${data.projects} (${data.connected_projects} by a connect)`],
						[
							"Timesheets",
							Object.entries(data.timesheets_by_status ?? {})
								.map(([status, n]) => `${n} ${status}`)
								.join(", ") || "None",
						],
						["Retention", s.retention_years ? `${s.retention_years} years` : "Default"],
						["Closing", s.closes_on ?? "Not closing"],
					]}
				/>
			</Panel>
			{s.owners === 0 ? <OrganisationActs summary={s} /> : null}
			<Panel title="Audit" note="What and when, never the details. Times are UTC.">
				{audit.error ? <Failed bare error={audit.error} onRetry={() => audit.refetch()} /> : null}
				{audit.data ? (
					<Table
						head={[day("When"), "Event", "Actor", "Subject"]}
						rows={audit.data.map((row) => [
							minuteOf(row.at),
							row.event,
							<Id key="actor">{row.actor_user_id ?? "system"}</Id>,
							<Id key="subject">{row.subject_user_id ?? "—"}</Id>,
						])}
						empty={<Empty title="Nothing recorded yet." />}
					/>
				) : audit.error ? null : (
					<Loading />
				)}
			</Panel>
		</Page>
	);
}

/**
 * The operator's organisation acts, offered only while there is no owner and
 * only on a request that passes the rule (docs/backoffice.md): each is
 * refused server-side with 409 ORGANISATION_HAS_OWNER the moment an owner
 * exists, whatever this page shows.
 */
function OrganisationActs({ summary }: { summary: OrganisationSummary }) {
	const [requester, setRequester] = useState("");
	const [closesOn, setClosesOn] = useState("");
	const confirmHint = "Type the organisation's name to confirm";
	return (
		<Panel
			danger
			title="What you can do while no owner is left"
			note="Only when asked. Each one is refused the moment an owner exists."
		>
			<CommandForm
				name="organisation.grant_owner"
				label="Grant the owner role"
				action="Grant the role"
				args={{ organisation_id: summary.id, user_id: requester }}
				confirmHint={confirmHint}
				invalidates={["organisation", "organisations", "attention"]}
				fields={
					<TextField
						label="The requester's account id"
						value={requester}
						onChange={(e) => setRequester(e.target.value)}
						className="min-w-[15rem] flex-1"
					/>
				}
			/>
			<CommandForm
				name="organisation.begin_closing"
				label="Start or move a closing notice"
				action="Set the notice"
				args={{ organisation_id: summary.id, closes_on: closesOn || null }}
				confirmHint={confirmHint}
				invalidates={["organisation", "organisations"]}
				fields={
					<TextField
						label="Closes on"
						type="date"
						value={closesOn}
						onChange={(e) => setClosesOn(e.target.value)}
					/>
				}
			/>
			<CommandForm
				name="organisation.cancel_closing"
				label="Cancel the closing notice"
				action="Cancel the notice"
				args={{ organisation_id: summary.id }}
				invalidates={["organisation", "organisations"]}
			/>
			<CommandForm
				name="organisation.delete"
				label="Queue deletion"
				about="Waits out a 1-day window before it runs."
				action="Queue the deletion"
				done="Queued. Cancel it from Jobs inside the day."
				args={{ organisation_id: summary.id }}
				confirmHint={confirmHint}
				invalidates={["organisation", "organisations", "operator-jobs"]}
			/>
			<CommandForm
				name="retention.purge"
				label="Queue a retention purge"
				about="Waits out a 1-day window before it runs."
				action="Queue the purge"
				done="Queued. Cancel it from Jobs inside the day."
				args={{ organisation_id: summary.id }}
				confirmHint={confirmHint}
				invalidates={["operator-jobs"]}
			/>
		</Panel>
	);
}
