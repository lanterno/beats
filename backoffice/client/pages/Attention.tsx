/**
 * The landing page: the reason to open the control plane. Each row is a
 * count, linking to the thing. The deploy-state row waits on
 * roadmaps/secret-manager.md; until then this links to the Cloud Run console.
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { get } from "@/shared/api/client";
import type { AttentionCounts } from "@/shared/api/schema";
import { API_LOG, logsQuery } from "@/shared/lib/console";
import { Failed, Loading, Section, Table } from "@/shared/ui";

const CLOUD_RUN = "https://console.cloud.google.com/run?project=beats-476914";

// Accounts a per-account write limit refused. Not a count in the table
// above: nothing stores a refusal, by the decision in docs/backoffice.md
// § *Abuse* — the account is in the log line and in no document, so the
// question "which accounts, this week" is a log query and not a number.
const REFUSALS = logsQuery(`${API_LOG}\ntextPayload:"WRITE_LIMIT_REFUSED"`, 7);

export function Attention() {
	const { data, error } = useQuery({
		queryKey: ["attention"],
		queryFn: () => get<AttentionCounts>("/api/operator/attention"),
	});
	if (error) return <Failed error={error} />;
	if (!data) return <Loading />;

	const rows: Array<[string, number, string]> = [
		["Organisations with no owner", data.organisations_without_owner, "/organisations"],
		[
			"Organisations whose every owner is suspended",
			data.organisations_all_owners_suspended,
			"/organisations",
		],
		["Queued jobs inside their window", data.jobs_queued, "/compliance"],
		["Failed jobs", data.jobs_failed, "/compliance"],
		[
			"Approvals superseded and never reopened (30 days)",
			data.approvals_superseded_over_30d,
			"/organisations",
		],
		[
			"Absence requests pending more than 14 days",
			data.absence_requests_pending_over_14d,
			"/organisations",
		],
		["Accounts at 80% of their coach cap or past it", data.accounts_near_coach_cap, "/abuse"],
	];

	return (
		<>
			<Section title="Needs attention">
				<Table
					head={["What", "Count"]}
					rows={rows.map(([label, count, to]) => [
						<Link key={label} to={to} className="underline decoration-neutral-300">
							{label}
						</Link>,
						<span key={`${label}-n`} className={count > 0 ? "font-semibold" : "text-neutral-400"}>
							{count}
						</span>,
					])}
				/>
			</Section>
			<Section title="Writes refused by a per-account limit">
				<p className="p-3 text-sm text-neutral-500">
					Kept in the log, never in a document, so this is a query rather than a count:{" "}
					<a href={REFUSALS} className="underline">
						the accounts refused in the last 7 days
					</a>
					. Empty until a <code>WRITES_PER_MINUTE_*</code> ceiling is set.
				</p>
			</Section>
			<Section title="Deploy state">
				<p className="p-3 text-sm text-neutral-500">
					Waits on the API's secrets leaving its Cloud Run spec (roadmaps/secret-manager.md). Until
					then:{" "}
					<a href={CLOUD_RUN} className="underline">
						the Cloud Run console
					</a>
					.
				</p>
			</Section>
		</>
	);
}
