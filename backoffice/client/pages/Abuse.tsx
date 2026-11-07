/**
 * Detection by outlier rather than by a guessed threshold: who is far from
 * the median on the axes a hostile or broken account shows on. The controls
 * (limits, suspension, revoking one device) live on the account's page.
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { get } from "@/shared/api/client";
import type { AbuseReport } from "@/shared/api/schema";
import { API_LOG, logsQuery, metricChart } from "@/shared/lib/console";
import { Failed, Loading, Section, Table } from "@/shared/ui";

// Import sizes are the one axis on this page with no row: a restore's size
// is a fact about a request, not about what an account holds, so it is
// logged and counted and never stored (docs/backoffice.md § *Abuse*).
const IMPORTS = logsQuery(`${API_LOG}\ntextPayload:"IMPORT_RECEIVED"`, 30);
const IMPORT_SIZES = metricChart("beats-api/import_bytes");

function AccountRows({
	rows,
	unit,
}: {
	rows: Array<{ user_id: string; value: number }>;
	unit: string;
}) {
	return (
		<Table
			head={["Account", unit]}
			rows={rows.map((r) => [
				<Link key={r.user_id} to={`/accounts/${r.user_id}`} className="underline">
					<code className="text-xs">{r.user_id}</code>
				</Link>,
				r.value,
			])}
		/>
	);
}

export function Abuse() {
	const { data, error } = useQuery({
		queryKey: ["abuse"],
		queryFn: () => get<AbuseReport>("/api/operator/abuse"),
	});
	if (error) return <Failed error={error} />;
	if (!data) return <Loading />;

	return (
		<>
			<Section title="Coach spend this month">
				<AccountRows rows={data.coach_spend_per_account} unit="USD" />
			</Section>
			<Section title="Flow windows today">
				<AccountRows rows={data.flow_windows_per_account_today} unit="Windows" />
			</Section>
			<Section title="Sessions created, last 7 days">
				<AccountRows rows={data.sessions_created_7d_per_account} unit="Sessions" />
			</Section>
			<Section title="Report links minted">
				<AccountRows rows={data.report_links_per_account} unit="Links" />
			</Section>
			<Section title="Webhook destinations, by domain">
				<Table
					head={["Domain", "Webhooks"]}
					rows={data.webhook_domains.map((d) => [d.domain, d.value])}
				/>
			</Section>
			<Section title="Paired devices">
				<AccountRows rows={data.devices_per_account} unit="Devices" />
			</Section>
			<Section title="Backup restores, by size">
				<p className="p-3 text-sm text-neutral-500">
					<a href={IMPORT_SIZES} className="underline">
						The spread over time
					</a>
					, or{" "}
					<a href={IMPORTS} className="underline">
						each restore of the last 30 days
					</a>{" "}
					with the account that sent it. Neither is stored: a size is a fact about a request.
				</p>
			</Section>
			<Section title="Signups per day, last 90 days">
				<Table head={["Day", "Signups"]} rows={data.signups_per_day.map((d) => [d.day, d.value])} />
			</Section>
		</>
	);
}
