/**
 * The organisations the platform runs for: rosters, states and the audit of
 * acts — settings and counts, never a figure from anyone's record. The
 * operator acts here only for an organisation with no owner, and only when
 * asked (step 3's commands; this page is the read).
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { get } from "@/shared/api/client";
import type { OrgAuditRow, OrganisationDetail, OrganisationSummary } from "@/shared/api/schema";
import { dayOf } from "@/shared/lib/format";
import { Facts, Failed, Loading, Section, Table } from "@/shared/ui";
import { CommandForm } from "@/shared/ui/CommandForm";

function roles(byRole: Record<string, number> | undefined): string {
	const entries = Object.entries(byRole ?? {});
	if (entries.length === 0) return "nobody";
	return entries.map(([role, n]) => `${n} ${role}`).join(", ");
}

export function Organisations() {
	const { data, error } = useQuery({
		queryKey: ["organisations"],
		queryFn: () => get<OrganisationSummary[]>("/api/operator/organisations"),
	});
	if (error) return <Failed error={error} />;
	if (!data) return <Loading />;

	return (
		<Section title="Organisations">
			<Table
				head={["Name", "Created", "Members", "Assignments", "Retention", "State"]}
				rows={data.map((o) => [
					<Link key={o.id} to={`/organisations/${o.id}`} className="underline">
						{o.name}
					</Link>,
					dayOf(o.created_at),
					roles(o.members_by_role),
					o.active_assignments,
					o.retention_years ? `${o.retention_years} years` : "default",
					o.closes_on
						? `closing ${o.closes_on}`
						: o.owners === 0
							? "no owner"
							: o.all_owners_suspended
								? "every owner suspended"
								: "open",
				])}
			/>
		</Section>
	);
}

export function Organisation() {
	const { id } = useParams();
	const { data, error } = useQuery({
		queryKey: ["organisation", id],
		queryFn: () => get<OrganisationDetail>(`/api/operator/organisations/${id}`),
	});
	const audit = useQuery({
		queryKey: ["organisation-audit", id],
		queryFn: () => get<OrgAuditRow[]>(`/api/operator/organisations/${id}/audit`),
	});
	if (error) return <Failed error={error} />;
	if (!data) return <Loading />;
	const s = data.summary;

	return (
		<>
			<Section title={s.name}>
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
								.join(", ") || "none",
						],
						["Retention", s.retention_years ? `${s.retention_years} years` : "default"],
						["Closing", s.closes_on ?? "—"],
					]}
				/>
			</Section>
			{s.owners === 0 ? <OrganisationActs summary={s} /> : null}
			<Section title="Audit — what and when, never the details">
				{audit.error ? <Failed error={audit.error} /> : null}
				{audit.data ? (
					<Table
						head={["When", "Event", "Actor", "Subject"]}
						rows={audit.data.map((row) => [
							row.at,
							row.event,
							row.actor_user_id ?? "system",
							row.subject_user_id ?? "—",
						])}
					/>
				) : (
					<Loading />
				)}
			</Section>
		</>
	);
}

/**
 * The operator's organisation acts, offered only while there is no owner and
 * only on a request that passes the rule (roadmaps/backoffice.md): each is
 * refused server-side with 409 ORGANISATION_HAS_OWNER the moment an owner
 * exists, whatever this page shows.
 */
function OrganisationActs({ summary }: { summary: OrganisationSummary }) {
	const [requester, setRequester] = useState("");
	const [closesOn, setClosesOn] = useState("");
	return (
		<Section title="Acts — only because no owner is left, and only when asked">
			<CommandForm
				name="organisation.grant_owner"
				label="Grant the owner role"
				args={{ organisation_id: summary.id, user_id: requester }}
				confirmHint="type the organisation's name"
				invalidates={["organisation", "organisations", "attention"]}
				fields={
					<input
						value={requester}
						onChange={(e) => setRequester(e.target.value)}
						placeholder="the requester's account id"
						className="border border-neutral-300 rounded px-2 py-1 text-sm w-64"
					/>
				}
			/>
			<CommandForm
				name="organisation.begin_closing"
				label="Start or move a closing notice"
				args={{ organisation_id: summary.id, closes_on: closesOn || null }}
				confirmHint="type the organisation's name"
				invalidates={["organisation", "organisations"]}
				fields={
					<input
						type="date"
						value={closesOn}
						onChange={(e) => setClosesOn(e.target.value)}
						className="border border-neutral-300 rounded px-2 py-1 text-sm"
					/>
				}
			/>
			<CommandForm
				name="organisation.cancel_closing"
				label="Cancel the closing notice"
				args={{ organisation_id: summary.id }}
				invalidates={["organisation", "organisations"]}
			/>
		</Section>
	);
}
