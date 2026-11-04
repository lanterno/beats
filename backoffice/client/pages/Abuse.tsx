/**
 * Detection by outlier rather than by a guessed threshold: who is far from
 * the median on the axes a hostile or broken account shows on. The controls
 * (limits, suspension, revoking one device) arrive with step 3's commands.
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { get } from "@/shared/api/client";
import type { AbuseReport } from "@/shared/api/schema";
import { Failed, Loading, Section, Table } from "@/shared/ui";

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
			<Section title="Signups per day, last 90 days">
				<Table head={["Day", "Signups"]} rows={data.signups_per_day.map((d) => [d.day, d.value])} />
			</Section>
		</>
	);
}
