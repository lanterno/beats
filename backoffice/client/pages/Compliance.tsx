/**
 * Privacy and compliance: what was promised about other people's data, and
 * the one control that keeps the promise — the platform-wide retention
 * purge, never scheduled, because PRIVACY.md and the DPA say an operator
 * runs it.
 *
 * The line itself is on this page because it is a promise and not a
 * feature: an operator reading it should be able to tell, before opening
 * any other page, which questions this surface will refuse to answer.
 *
 * The erasure request log lives here too: a mail gets a date the day it
 * arrives, so the legal month is visible before anything is queued. What the
 * mock shows and this does not: backup and restore-drill dates, and a
 * documents checklist. No route answers them, and a date with no source is
 * worse here than on any other page.
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { get } from "@/shared/api/client";
import type { ErasureRequestState } from "@/shared/api/schema";
import { dayOf } from "@/shared/lib/format";
import {
	buttonClass,
	Chip,
	Empty,
	Failed,
	Id,
	Loading,
	Page,
	Pair,
	Panel,
	Prose,
	Table,
} from "@/shared/ui";
import { CommandForm } from "@/shared/ui/CommandForm";

/** How many days from the mail the law allows, and the day it runs out. */
export const LEGAL_MONTH_DAYS = 30;

export function deadlineOf(received: string): string {
	const day = new Date(`${received}T00:00:00Z`);
	day.setUTCDate(day.getUTCDate() + LEGAL_MONTH_DAYS);
	return day.toISOString().slice(0, 10);
}

/** Where a request stands, in words: the status, and the days it has waited. */
export function requestState(row: ErasureRequestState, today: string): string {
	if (row.status === "closed") return `Closed: ${row.closed_reason ?? "—"}`;
	if (row.status === "erasure_ran") return "Erasure ran — close it";
	if (row.status === "erasure_queued") return "Erasure queued";
	const waited = Math.floor(
		(Date.parse(`${today}T00:00:00Z`) - Date.parse(`${row.received_on}T00:00:00Z`)) / 86_400_000,
	);
	return `Open, day ${waited + 1} of ${LEGAL_MONTH_DAYS}`;
}

function ErasureRequests() {
	const requests = useQuery({
		queryKey: ["erasure-requests"],
		queryFn: () => get<ErasureRequestState[]>("/api/operator/erasure-requests"),
	});
	if (requests.error)
		return <Failed bare error={requests.error} onRetry={() => requests.refetch()} />;
	if (!requests.data) return <Loading />;
	const today = new Date().toISOString().slice(0, 10);
	const open = requests.data.filter((r) => r.status !== "closed");
	return (
		<>
			<Table
				head={["Reference", "Received", "Deadline", "Account", "State", ""]}
				rows={open.map((r) => [
					r.reference,
					dayOf(r.received_on),
					deadlineOf(r.received_on),
					r.subject_id ? (
						<Link key="a" to={`/accounts/${r.subject_id}`} className="link">
							<Id>{r.subject_id}</Id>
						</Link>
					) : (
						"None"
					),
					<Chip key="s" tone={r.status === "open" ? "owed" : "quiet"}>
						{requestState(r, today)}
					</Chip>,
					<Link
						key="c"
						to={`/review/erasure_request.close/${r.id}`}
						className={buttonClass("secondary")}
					>
						Close
					</Link>,
				])}
				empty={
					<Empty title="No open request.">
						Log one the day its mail arrives, so the deadline is visible before anything is queued.
					</Empty>
				}
			/>
			<div className="flex flex-wrap items-center gap-3 px-6 pb-5">
				<Link to="/review/erasure_request.log/new" className={buttonClass("primary")}>
					Log a request
				</Link>
				<span className="text-[13px] text-ink-muted">
					{requests.data.length - open.length} closed, kept a year each.
				</span>
			</div>
		</>
	);
}

/** docs/backoffice.md § The line, as the operator reads it. */
const LINE: Array<[sees: string, never: string]> = [
	["Account id, address, created, the day last seen, state", "Sessions, their times, their notes"],
	["Counts of projects, sessions, devices and organisations", "Project names, tags, absence notes"],
	["Which integrations are connected", "Any integration's token or what it fetched"],
	["Webhook destinations, by domain", "A webhook's full URL, or what was sent to it"],
	["Coach spend, tokens and model", "Any coach conversation or memory"],
	["Organisation name, settings, members, roles", "Clients, rates, amounts, report contents"],
	["An organisation's audit: what, by whom, to whom, when", "The details of one of its events"],
	["How many biometric rows exist", "Any biometric value"],
];

export function Compliance() {
	return (
		<Page
			title="Privacy and compliance"
			lead="What was promised about other people's data, and the one act that keeps it."
		>
			<Panel
				danger
				title="Retention purge, platform-wide"
				note="Never scheduled, by decision: PRIVACY.md and the DPA promise an operator runs it."
			>
				<CommandForm
					name="retention.purge"
					label="Purge every organisation"
					about="Every organisation's records past its own retention period, and this back office's audit past four years."
					action="Queue the purge"
					done="Queued. Cancel it from Jobs and windows until its window ends."
					args={{ organisation_id: null }}
					confirmHint='Type "all" to confirm'
					invalidates={["operator-jobs", "attention"]}
				/>
			</Panel>
			<Panel
				title="What this back office may see"
				note="The line between running the service and reading someone's life. It is held by construction and by a test that plants a sentinel in every right-hand thing and greps every page for it."
			>
				<div className="overflow-x-auto pb-3">
					<table className="w-full text-[14px]">
						<thead>
							<tr className="text-left text-[13px]">
								<th scope="col" className="px-2.5 py-1.5 pl-6 font-medium text-leaf-ink">
									It sees
								</th>
								<th scope="col" className="px-2.5 py-1.5 pr-6 font-medium text-persimmon-ink">
									It never sees
								</th>
							</tr>
						</thead>
						<tbody>
							{LINE.map(([sees, never]) => (
								<tr key={sees} className="border-t border-hairline">
									<td className="w-1/2 px-2.5 py-[7px] pl-6 align-top">{sees}</td>
									<td className="w-1/2 px-2.5 py-[7px] pr-6 align-top">{never}</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
			</Panel>
			<Panel
				title="Erasure requests"
				note="They arrive by email at the address in PRIVACY.md. The clock runs from the mail: a request with nothing queued after 14 days is on the queue. A reference and an id, never an address."
			>
				<ErasureRequests />
			</Panel>
			<Pair>
				<Panel title="Reading a document in the database">
					<Prose>
						Nothing above stops it, and PRIVACY.md says so rather than pretending otherwise. The
						point of these pages is that the question is answered here instead.
					</Prose>
				</Panel>
				<Panel title="Queued erasures">
					<Prose>
						An erasure you have queued is on Jobs and windows, where its seven-day window is
						running; the state column above reads it from there.
					</Prose>
				</Panel>
			</Pair>
		</Page>
	);
}
