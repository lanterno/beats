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
import type { AbuseReport, SignupWave } from "@/shared/api/schema";
import { API_LOG, logsQuery, metricChart } from "@/shared/lib/console";
import { counted, dollars, everyDay } from "@/shared/lib/format";
import {
	buttonClass,
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

/**
 * The hour's sign-ups in words. The network is "Network A", never its key;
 * the key travels only into the slow-down's review, as the control's subject.
 */
export function waveSentence(wave: SignupWave): string {
	const usual = wave.usual === 0 ? "usually none" : `usually about ${wave.usual}`;
	const head = `${counted(wave.completed, "account was", "accounts were")} created this hour, ${usual}.`;
	if (wave.largest_group === null || wave.largest_group === undefined) {
		return `${head} No network is large enough to show.`;
	}
	return `${head} Network A is ${wave.largest_group} of them. Of all ${wave.completed}, ${wave.accounts_with_writes} ${wave.accounts_with_writes === 1 ? "has" : "have"} written anything.`;
}

function SignupWavePanel({ wave }: { wave: SignupWave }) {
	const slow = wave.largest_key
		? `/review/control.set/signups?network=${encodeURIComponent(wave.largest_key)}`
		: null;
	return (
		<Panel
			title="Sign-ups this hour, by network"
			note="A network is an address cut to its /24 or /48 and hashed with a key that changes at UTC midnight. No account is joined to a network anywhere: this is a shape in the hour, not a list of people. Offices, universities, carrier networks and a company onboarding its staff all look like this."
		>
			<Prose>{waveSentence(wave)}</Prose>
			{slow ? (
				<div className="flex flex-wrap items-center gap-3 px-6 pb-5">
					<Link to={slow} className={buttonClass("secondary")}>
						Slow sign-ups from Network A
					</Link>
					<span className="text-[13px] text-ink-muted">
						A ceiling an hour for that network alone; nobody is blocked, and it ends at UTC midnight
						at the latest, when the key stops matching.
					</span>
				</div>
			) : null}
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
			{data.signup_wave ? <SignupWavePanel wave={data.signup_wave} /> : null}
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
