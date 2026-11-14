/**
 * Trust and safety (docs/backoffice.md § The pages): who is using far more
 * than everyone else, judged from counts alone. A sentence first, then the
 * sign-up signal with its one act, then a single table with a tab per axis,
 * then the two signals kept only in the logs. Drawn from
 * docs/backoffice-mock/screens/Trust.png, less what nothing serves:
 *
 * - the sign-up chart is by day over 90 days, because the read serves
 *   sign-ups by day; this hour is the sentence beneath it;
 * - each axis is its highest 20 and nothing else, so the table has no
 *   "against the median" column, and no "already restricted" one, which
 *   would be the restrictions across accounts that docs/backoffice.md says
 *   no page lists;
 * - writes refused per route are a link, as they are on Today: nothing
 *   stores a refusal.
 *
 * The controls on an account (limits, suspension, revoking one device) stay
 * on its own page, so the dangerous act is never a click away from a list
 * of suspects.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { get } from "@/shared/api/client";
import type { AbuseReport, SignupWave } from "@/shared/api/schema";
import { API_LOG, logsQuery, metricChart } from "@/shared/lib/console";
import { counted, dollars, everyDay } from "@/shared/lib/format";
import { handOver } from "@/shared/lib/handover";
import {
	buttonClass,
	DayBars,
	Empty,
	Failed,
	figure,
	Id,
	Loading,
	Page,
	Panel,
	Prose,
	Table,
} from "@/shared/ui";

// A refusal and a restore's size are facts about a request, logged and
// counted and never stored (docs/backoffice.md § The pages, Trust and
// safety), so they are links rather than rows.
const REFUSALS = logsQuery(`${API_LOG}\ntextPayload:"WRITE_LIMIT_REFUSED"`, 7);
const REFUSALS_BY_ROUTE = metricChart("beats-api/write_limit_refusals");
const IMPORTS = logsQuery(`${API_LOG}\ntextPayload:"IMPORT_RECEIVED"`, 30);
const IMPORT_SIZES = metricChart("beats-api/import_bytes");

/** The page's first sentence. Only the sign-up signal is judged: the table
 * is a ranking with nothing to hold it against, so the sentence never calls
 * it ordinary. */
export function trustHeadline(wave: SignupWave | null | undefined): string {
	if (!wave) return "Who is using far more than everyone else.";
	if (wave.largest_group !== null && wave.largest_group !== undefined) {
		return "One network stands out in this hour's sign-ups.";
	}
	if (wave.completed > wave.usual) return "More people are signing up than usual this hour.";
	return "This hour's sign-ups are ordinary.";
}

/** "84 sign-ups since 09:00 UTC, usually about 14". */
export function waveTitle(wave: SignupWave): string {
	const usual = wave.usual === 0 ? "usually none" : `usually about ${wave.usual}`;
	return `${counted(wave.completed, "sign-up", "sign-ups")} since ${wave.hour.slice(11, 13)}:00 UTC, ${usual}`;
}

/**
 * The hour's sign-ups in words. The network is "Network A", never its key;
 * the key travels only into the slow-down's review, in navigation state.
 */
export function waveSentence(wave: SignupWave): string {
	if (wave.largest_group === null || wave.largest_group === undefined) {
		return "No network is large enough to show.";
	}
	return `Network A is ${wave.largest_group} of them. Of all ${wave.completed} accounts created this hour, ${wave.accounts_with_writes} ${wave.accounts_with_writes === 1 ? "has" : "have"} written anything; which of those are Network A's is not recorded, and will not be.`;
}

/** One tab per axis, each the read's highest 20. */
export const AXES = [
	{ id: "coach", label: "Coach spend", head: "This month", over: "this month" },
	{ id: "flow", label: "Flow windows", head: "Today", over: "today" },
	{ id: "sessions", label: "Sessions", head: "Last 7 days", over: "in the last 7 days" },
	{ id: "reports", label: "Report links", head: "Links", over: "by report links held" },
	{
		id: "webhooks",
		label: "Webhook domains",
		head: "Webhooks",
		over: "by webhooks pointing there",
	},
	{ id: "devices", label: "Devices", head: "Paired", over: "by devices paired" },
] as const;

export type Axis = (typeof AXES)[number]["id"];

/** One axis's rows: an account and a figure, or, for webhooks, a domain and a count. */
export function axisRows(
	report: AbuseReport,
	axis: Axis,
): Array<{ user_id?: string; domain?: string; value: number }> {
	switch (axis) {
		case "coach":
			return report.coach_spend_per_account;
		case "flow":
			return report.flow_windows_per_account_today;
		case "sessions":
			return report.sessions_created_7d_per_account;
		case "reports":
			return report.report_links_per_account;
		case "webhooks":
			return report.webhook_domains;
		case "devices":
			return report.devices_per_account;
	}
}

/** The table's note: how many it shows, and over what. */
export function axisNote(axis: Axis, shown: number): string {
	const { over } = AXES.find((a) => a.id === axis) ?? AXES[0];
	if (shown === 0) return `Nothing to rank ${over}.`;
	return shown === 1 ? `The only one ${over}.` : `The highest ${shown} ${over}.`;
}

function SignupPanel({ report }: { report: AbuseReport }) {
	const wave = report.signup_wave;
	const days = everyDay(report.signups_per_day, 90, new Date());
	const total = days.reduce((sum, d) => sum + d.value, 0);
	const busiest = days.reduce((best, d) => (d.value > best.value ? d : best), days[0]);
	const said =
		total === 0
			? "Nobody has signed up in the last 90 days."
			: `${counted(total, "person", "people")} signed up in the last 90 days. The busiest day was ${busiest.day}, with ${busiest.value}.`;
	const slow = wave?.largest_key
		? handOver("/review/control.set/signups", { network: wave.largest_key })
		: null;
	return (
		<Panel raised title={wave ? waveTitle(wave) : "Sign-ups"} note={said}>
			{total > 0 ? <DayBars days={days} said={said} unit="Sign-ups" /> : null}
			{wave ? (
				<div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-6 pb-5">
					<p className="min-w-[16rem] flex-1 text-[15px] leading-relaxed">
						{waveSentence(wave)} Offices, universities, carrier networks and an organisation
						onboarding its staff all look like this.
					</p>
					{slow ? (
						<Link {...slow} className={buttonClass("primary")}>
							Slow sign-ups from Network A
						</Link>
					) : null}
				</div>
			) : (
				<div className="pb-5" />
			)}
		</Panel>
	);
}

function OutlierTable({ report }: { report: AbuseReport }) {
	const [axis, setAxis] = useState<Axis>("coach");
	const spec = AXES.find((a) => a.id === axis) ?? AXES[0];
	const rows = axisRows(report, axis);
	const show = axis === "coach" ? dollars : String;
	return (
		<Panel title="Far above everyone else" note={axisNote(axis, rows.length)}>
			<div className="px-6 pb-3">
				{/* biome-ignore lint/a11y/useSemanticElements: a fieldset cannot be a rounded flex track across browsers */}
				<div
					role="group"
					aria-label="Which count"
					className="inline-flex flex-wrap gap-1 rounded-[22px] bg-wash p-1"
				>
					{AXES.map((a) => (
						<button
							key={a.id}
							type="button"
							aria-pressed={a.id === axis}
							onClick={() => setAxis(a.id)}
							className={`inline-flex h-9 items-center rounded-full px-3.5 text-[14px] ${
								a.id === axis
									? "bg-panel-solid font-bold shadow-[var(--shadow-hairline)]"
									: "hover:bg-wash-strong"
							}`}
						>
							{a.label}
						</button>
					))}
				</div>
			</div>
			<Table
				head={[axis === "webhooks" ? "Domain" : "Account", figure(spec.head)]}
				rows={rows.map((r) => [
					r.user_id ? (
						<Link key={r.user_id} to={`/accounts/${r.user_id}`} className="link">
							<Id>{r.user_id}</Id>
						</Link>
					) : (
						r.domain
					),
					show(r.value),
				])}
				empty={<Empty title={axisNote(axis, 0)} />}
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

	return (
		<Page
			title={trustHeadline(data.signup_wave)}
			lead="Who is using far more than everyone else, judged from counts alone. An outlier is a question, not a verdict: offices, teams and heavy users sit out here too."
		>
			<SignupPanel report={data} />
			<OutlierTable report={data} />
			<Panel
				title="Writes refused by the limits"
				note="Counted by route and kept in the logs, never stored against an account."
			>
				<Prose>
					It stays empty until a write limit is set. Restores are logged the same way, with their
					size:{" "}
					<a href={IMPORTS} className="link">
						each restore of the last 30 days
					</a>
					, with the account that sent it.
				</Prose>
				<div className="flex flex-wrap gap-2 px-6 pb-5">
					<a href={REFUSALS} className={buttonClass("secondary")}>
						Open the query in Cloud Logging
					</a>
					<a href={REFUSALS_BY_ROUTE} className={buttonClass("secondary")}>
						See them by route
					</a>
					<a href={IMPORT_SIZES} className={buttonClass("secondary")}>
						See restores by size
					</a>
				</div>
			</Panel>
		</Page>
	);
}
