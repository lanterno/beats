/**
 * The landing page: the reason to open the control plane. It says how many
 * things need the operator, then each one with the way to it, and the checks
 * that came back clear go quietly underneath. The sun is on the first thing
 * to do, or in the sky when there is nothing. The deploy-state card waits on
 * roadmaps/secret-manager.md; until then it links to the Cloud Run console.
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { get } from "@/shared/api/client";
import type { AttentionCounts } from "@/shared/api/schema";
import { API_LOG, logsQuery } from "@/shared/lib/console";
import { counted } from "@/shared/lib/format";
import { buttonClass, Failed, Loading, Page, Pair, Panel, Prose } from "@/shared/ui";
import { CheckIcon } from "@/shared/ui/icons";

const CLOUD_RUN = "https://console.cloud.google.com/run?project=beats-476914";

// Accounts a per-account write limit refused. Not a count on this page:
// nothing stores a refusal, by the decision in docs/backoffice.md § *Abuse*
// — the account is in the log line and in no document, so the question
// "which accounts, this week" is a log query and not a number.
const REFUSALS = logsQuery(`${API_LOG}\ntextPayload:"WRITE_LIMIT_REFUSED"`, 7);

interface Check {
	count: keyof AttentionCounts;
	/** The sentence after the figure. */
	says: (n: number) => string;
	/** The sentence when the figure is 0. */
	clear: string;
	to: string;
	open: string;
}

const CHECKS: Check[] = [
	{
		count: "organisations_without_owner",
		says: (n) => (n === 1 ? "organisation has no owner" : "organisations have no owner"),
		clear: "Every organisation has an owner",
		to: "/organisations",
		open: "Open organisations",
	},
	{
		count: "organisations_all_owners_suspended",
		says: (n) =>
			n === 1
				? "organisation has only suspended owners"
				: "organisations have only suspended owners",
		clear: "No organisation is down to suspended owners",
		to: "/organisations",
		open: "Open organisations",
	},
	{
		count: "jobs_queued",
		says: (n) =>
			n === 1 ? "job is queued inside its window" : "jobs are queued inside their window",
		clear: "No job is waiting out its window",
		to: "/jobs",
		open: "Open jobs",
	},
	{
		count: "jobs_failed",
		says: (n) => (n === 1 ? "job failed" : "jobs failed"),
		clear: "No job has failed",
		to: "/jobs",
		open: "Open jobs",
	},
	{
		count: "approvals_superseded_over_30d",
		says: (n) =>
			n === 1
				? "approval was superseded over 30 days ago and never reopened"
				: "approvals were superseded over 30 days ago and never reopened",
		clear: "No approval has sat superseded for over 30 days",
		to: "/organisations",
		open: "Open organisations",
	},
	{
		count: "absence_requests_pending_over_14d",
		says: (n) =>
			n === 1
				? "absence request has waited more than 14 days"
				: "absence requests have waited more than 14 days",
		clear: "No absence request has waited more than 14 days",
		to: "/organisations",
		open: "Open organisations",
	},
	{
		count: "accounts_near_coach_cap",
		says: (n) =>
			n === 1
				? "account is at 80% of its coach cap or past it"
				: "accounts are at 80% of their coach cap or past it",
		clear: "No account is near its coach cap",
		to: "/trust",
		open: "Open trust and safety",
	},
];

export function Attention() {
	const { data, error, refetch } = useQuery({
		queryKey: ["attention"],
		queryFn: () => get<AttentionCounts>("/api/operator/attention"),
	});
	if (error) return <Failed error={error} onRetry={() => refetch()} />;
	if (!data) return <Loading />;

	const needing = CHECKS.filter((check) => data[check.count] > 0);
	const clear = CHECKS.filter((check) => data[check.count] === 0);
	const total = needing.reduce((sum, check) => sum + data[check.count], 0);

	return (
		<Page
			title={
				total === 0
					? "Nothing needs you right now."
					: `${counted(total, "thing needs", "things need")} you.`
			}
			lead={
				total === 0
					? `All ${CHECKS.length} checks came back clear.`
					: "Start at the top. Each button opens the page where you can act."
			}
			aside={
				total === 0 ? (
					<div aria-hidden="true" className="size-[72px] shrink-0 rounded-full bg-sun" />
				) : undefined
			}
		>
			{needing.length > 0 ? (
				<Panel raised>
					<ul className="px-6 py-2">
						{needing.map((check, i) => (
							<li
								key={check.count}
								className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-hairline py-3 first:border-0"
							>
								<span className="min-w-[2ch] font-heading text-[28px] leading-none font-extrabold">
									{data[check.count]}
								</span>
								<span className="min-w-[12rem] flex-1 text-[15px]">
									{check.says(data[check.count])}
								</span>
								<Link to={check.to} className={buttonClass(i === 0 ? "primary" : "secondary")}>
									{check.open}
								</Link>
							</li>
						))}
					</ul>
				</Panel>
			) : null}
			{clear.length > 0 ? (
				<Panel title={total === 0 ? "What was checked" : "Clear"} raised={total === 0}>
					<ul className="grid gap-x-6 px-6 pb-4 md:grid-cols-2">
						{clear.map((check) => (
							<li key={check.count} className="flex items-start gap-2 py-1 text-[14px]">
								<CheckIcon className="mt-0.5 size-4 shrink-0 text-leaf-ink" />
								{check.clear}
							</li>
						))}
					</ul>
				</Panel>
			) : null}
			<Pair>
				<Panel title="Writes refused by a per-account limit">
					<Prose>
						These live in the log, never in a document, so it's a query rather than a count:{" "}
						<a href={REFUSALS} className="link">
							the accounts refused in the last 7 days
						</a>
						. It stays empty until a <code>WRITES_PER_MINUTE_*</code> ceiling is set.
					</Prose>
				</Panel>
				<Panel title="Deploy state">
					<Prose>
						Not shown here yet: it waits on the API's secrets leaving its Cloud Run spec. Until
						then,{" "}
						<a href={CLOUD_RUN} className="link">
							open the Cloud Run console
						</a>
						.
					</Prose>
				</Panel>
			</Pair>
		</Page>
	);
}
