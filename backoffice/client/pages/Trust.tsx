/**
 * Trust and safety: detection by outlier rather than by a guessed
 * threshold — who is far from the median on the axes a hostile or broken
 * account shows on. The controls (limits, suspension, revoking one device)
 * live on the account's page, so the dangerous act is never a click away
 * from a list of suspects.
 */

import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { get } from "@/shared/api/client";
import type { AbuseReport } from "@/shared/api/schema";
import { API_LOG, logsQuery, metricChart } from "@/shared/lib/console";
import { counted, dollars, everyDay } from "@/shared/lib/format";
import {
	DayBars,
	Empty,
	Failed,
	figure,
	Id,
	Loading,
	Page,
	Pair,
	Panel,
	Prose,
	Table,
} from "@/shared/ui";

// Import sizes are the one axis on this page with no row: a restore's size
// is a fact about a request, not about what an account holds, so it is
// logged and counted and never stored (docs/backoffice.md § *Abuse*).
const IMPORTS = logsQuery(`${API_LOG}\ntextPayload:"IMPORT_RECEIVED"`, 30);
const IMPORT_SIZES = metricChart("beats-api/import_bytes");

function AccountRows({
	title,
	rows,
	unit,
	show = String,
	empty,
}: {
	title: string;
	rows: Array<{ user_id: string; value: number }>;
	unit: string;
	show?: (value: number) => ReactNode;
	empty: string;
}) {
	return (
		<Panel title={title}>
			<Table
				head={["Account", figure(unit)]}
				rows={rows.map((r) => [
					<Link key={r.user_id} to={`/accounts/${r.user_id}`} className="link">
						<Id>{r.user_id}</Id>
					</Link>,
					show(r.value),
				])}
				empty={<Empty title={empty} />}
			/>
		</Panel>
	);
}

export function Trust() {
	const { data, error, refetch } = useQuery({
		queryKey: ["abuse"],
		queryFn: () => get<AbuseReport>("/api/operator/abuse"),
	});
	if (error) return <Failed error={error} onRetry={() => refetch()} />;
	if (!data) return <Loading />;

	const days = everyDay(data.signups_per_day, 90, new Date());
	const signups = days.reduce((sum, d) => sum + d.value, 0);
	const busiest = days.reduce((best, d) => (d.value > best.value ? d : best), days[0]);
	const said =
		signups === 0
			? "Nobody has signed up in the last 90 days."
			: `${counted(signups, "person", "people")} signed up in the last 90 days. The busiest day was ${busiest.day}, with ${busiest.value}.`;

	return (
		<Page
			title="Trust and safety"
			lead="Who sits far from the median on the axes a hostile or broken account shows on. An outlier is a question, not a verdict: offices, teams and heavy users sit out here too. The controls are on each account's page."
		>
			<Panel raised title="Signups" note={said}>
				{signups > 0 ? (
					<DayBars days={days} said={said} unit="Signups" />
				) : (
					<div className="pb-5" />
				)}
			</Panel>
			<Pair>
				<AccountRows
					title="Coach spend this month"
					rows={data.coach_spend_per_account}
					unit="Spent"
					show={dollars}
					empty="Nobody has spent any coach budget this month."
				/>
				<AccountRows
					title="Flow windows today"
					rows={data.flow_windows_per_account_today}
					unit="Windows"
					empty="No flow windows have arrived today."
				/>
				<AccountRows
					title="Sessions created, last 7 days"
					rows={data.sessions_created_7d_per_account}
					unit="Sessions"
					empty="No sessions in the last 7 days."
				/>
				<AccountRows
					title="Report links minted"
					rows={data.report_links_per_account}
					unit="Links"
					empty="Nobody has minted a report link."
				/>
				<AccountRows
					title="Paired devices"
					rows={data.devices_per_account}
					unit="Devices"
					empty="No devices are paired."
				/>
				<Panel title="Webhook destinations, by domain">
					<Table
						head={["Domain", figure("Webhooks")]}
						rows={data.webhook_domains.map((d) => [d.domain, d.value])}
						empty={<Empty title="No webhooks point anywhere yet." />}
					/>
				</Panel>
			</Pair>
			<Panel title="Backup restores, by size">
				<Prose>
					<a href={IMPORT_SIZES} className="link">
						See the spread over time
					</a>
					, or{" "}
					<a href={IMPORTS} className="link">
						each restore of the last 30 days
					</a>{" "}
					with the account that sent it. Neither is stored: a size is a fact about a request.
				</Prose>
			</Panel>
		</Page>
	);
}
