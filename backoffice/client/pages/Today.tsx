/**
 * Today: the reason to open the control plane (docs/backoffice.md, stage
 * 1). One sentence saying what matters, the next things due off the queue,
 * the jobs waiting out a window, the last few things the back office did, and
 * what the platform costs. Every figure is one of the reads the other pages
 * already make; the mock's incident and release panels wait for their own
 * stages, and the deploy-state card waits on roadmaps/secret-manager.md.
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { get } from "@/shared/api/client";
import type { CapacityReport, QueueRow, ReleasesReport } from "@/shared/api/schema";
import { API_LOG, logsQuery } from "@/shared/lib/console";
import { dollars, formatBytes, minuteOf } from "@/shared/lib/format";
import { bucketOf, dueLabel, KINDS } from "@/shared/lib/queue";
import { releasesHeadline } from "@/shared/lib/releases";
import {
	buttonClass,
	Chip,
	day,
	Empty,
	Facts,
	Failed,
	Id,
	Loading,
	Page,
	Pair,
	Panel,
	Prose,
	Table,
} from "@/shared/ui";
import { HealthPanel } from "@/shared/ui/HealthPanel";

const CLOUD_RUN = "https://console.cloud.google.com/run?project=beats-476914";

// Accounts a per-account write limit refused. Not a count on this page:
// nothing stores a refusal, by the decision in docs/backoffice.md § *Abuse*
// — the account is in the log line and in no document, so the question
// "which accounts, this week" is a log query and not a number.
const REFUSALS = logsQuery(`${API_LOG}\ntextPayload:"WRITE_LIMIT_REFUSED"`, 7);

/** How many of the queue's rows Today shows before "Open the queue". */
const NEXT = 4;
/** How many audit rows. */
const RECENT = 5;

type Row = Record<string, unknown>;

/** The first sentence, from the queue alone. */
export function todayHeadline(rows: QueueRow[], now: Date): string {
	const first = rows[0];
	if (!first) return "Nothing needs you right now.";
	const over = rows.filter((row) => bucketOf(row, now) === "overdue").length;
	if (over > 0) {
		return over === 1 ? "One thing is overdue." : `${over} things are overdue.`;
	}
	return rows.length === 1 ? "One thing needs you." : `${rows.length} things need you.`;
}

/** The coach's cost since the 1st of this UTC month. */
export function monthSpend(capacity: CapacityReport, now: Date): number {
	const month = now.toISOString().slice(0, 7);
	return capacity.coach_cost
		.filter((c) => c.day.startsWith(month))
		.reduce((sum, c) => sum + c.cost_usd, 0);
}

interface PublicStatus {
	available: boolean;
	state: string;
	message: string;
	affected: string[];
	updated_at?: string | null;
	published: boolean;
}

/** What customers are being told (docs/status-page.md), and the way to say more. */
function StatusPanel() {
	const status = useQuery({
		queryKey: ["public-status"],
		queryFn: () => get<PublicStatus>("/api/operator/status"),
	});
	if (status.error) {
		return (
			<Panel title="What customers see">
				<Failed bare error={status.error} onRetry={() => status.refetch()} />
			</Panel>
		);
	}
	if (!status.data) return null;
	const s = status.data;
	if (!s.available) {
		return (
			<Panel title="What customers see">
				<Prose>
					This deployment has no status bucket, so there is no public status page to write to.
				</Prose>
			</Panel>
		);
	}
	const quiet = s.state === "operational";
	return (
		<Panel
			raised={!quiet}
			title="What customers see"
			note={
				s.published
					? `${s.state}${s.message ? ` — ${s.message}` : ""}${s.updated_at ? `, since ${minuteOf(s.updated_at)} UTC` : ""}.`
					: "Nothing has been published yet; the page reads as operational."
			}
		>
			<div className="flex flex-wrap items-center gap-3 px-6 pb-5">
				<Link
					to="/review/status.publish/public"
					className={buttonClass(quiet ? "secondary" : "primary")}
				>
					Publish an update
				</Link>
				{!quiet ? (
					<Link to="/review/status.clear/public" className={buttonClass("secondary")}>
						Say it is over
					</Link>
				) : null}
			</div>
		</Panel>
	);
}

export function Today() {
	const queue = useQuery({
		queryKey: ["operator-queue"],
		queryFn: () => get<QueueRow[]>("/api/operator/queue"),
	});
	const audit = useQuery({
		queryKey: ["operator-audit-recent"],
		queryFn: () => get<Row[]>(`/api/operator/audit?limit=${RECENT}`),
	});
	const releases = useQuery({
		queryKey: ["releases"],
		queryFn: () => get<ReleasesReport>("/api/operator/releases"),
	});
	const capacity = useQuery({
		queryKey: ["capacity"],
		queryFn: () => get<CapacityReport>("/api/operator/capacity"),
	});
	// The queue is the page's sentence; without it there is no page. The other
	// panels fail on their own, so one broken read does not hide the rest.
	if (queue.error) return <Failed error={queue.error} onRetry={() => queue.refetch()} />;
	if (!queue.data) return <Loading />;

	const now = new Date();
	const rows = queue.data;
	const waiting = rows.filter((row) => row.kind === "job_queued");
	const needing = rows.filter((row) => row.kind !== "job_queued");
	const first = needing[0];

	return (
		<Page
			title={todayHeadline(needing, now)}
			lead={
				first
					? `First: ${KINDS[first.kind].title(first)}. ${dueLabel(first, now)}.`
					: "Every check came back clear. Jobs waiting out a window are below, and need nothing until you want to stop one."
			}
			aside={
				first ? undefined : (
					<div aria-hidden="true" className="size-[72px] shrink-0 rounded-full bg-sun" />
				)
			}
		>
			{first ? (
				<Panel raised title="Due next">
					<ul className="px-6 pb-3">
						{needing.slice(0, NEXT).map((row, i) => (
							<li
								key={`${row.kind}:${row.subject_id}`}
								className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-hairline py-3 first:border-0"
							>
								<span className="min-w-[14rem] flex-1 text-[15px]">
									{KINDS[row.kind].title(row)}
								</span>
								<Chip tone={bucketOf(row, now) === "overdue" ? "owed" : "quiet"}>
									{dueLabel(row, now)}
								</Chip>
								<Link
									to={KINDS[row.kind].to(row)}
									className={buttonClass(i === 0 ? "primary" : "secondary")}
								>
									{KINDS[row.kind].next}
								</Link>
							</li>
						))}
					</ul>
					{needing.length > NEXT ? (
						<p className="px-6 pb-4 text-[14px]">
							<Link to="/queue" className="link">
								{needing.length - NEXT} more in the queue
							</Link>
						</p>
					) : null}
				</Panel>
			) : null}
			<Pair>
				<Panel title="Waiting out a window">
					<Table
						head={["Job", day("Runs")]}
						rows={waiting.map((row) => [<Id key="id">{row.subject_id}</Id>, minuteOf(row.due)])}
						empty={<Empty title="No job is waiting." />}
					/>
				</Panel>
				<Panel title="Storage and coach spend">
					{capacity.error ? (
						<Failed error={capacity.error} onRetry={() => capacity.refetch()} bare />
					) : capacity.data ? (
						<Facts
							items={[
								[
									"Database",
									formatBytes(capacity.data.collections.reduce((s, c) => s + c.storage_bytes, 0)),
								],
								["Coach, this month", dollars(monthSpend(capacity.data, now))],
							]}
						/>
					) : (
						<Loading />
					)}
				</Panel>
			</Pair>
			<HealthPanel />
			<StatusPanel />
			<Panel title="Done lately" note="The back office's last few commands. Times are UTC.">
				{audit.error ? (
					<Failed error={audit.error} onRetry={() => audit.refetch()} bare />
				) : (
					<Table
						head={[day("When"), "Command", "Subject", "By"]}
						rows={(audit.data ?? []).map((row) => [
							minuteOf(row.at),
							String(row.command ?? "—"),
							<Id key="s">{String(row.subject_id ?? "—")}</Id>,
							String(row.operator_email ?? "—"),
						])}
						empty={<Empty title="Nothing done yet." />}
					/>
				)}
			</Panel>
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
				<Panel title="Shipped">
					<Prose>
						{releases.data ? releasesHeadline(releases.data) : "Reading the releases…"}{" "}
						<Link to="/releases" className="link">
							Every release
						</Link>
						. Whether a revision became ready waits on the API's secrets leaving its Cloud Run spec;
						until then,{" "}
						<a href={CLOUD_RUN} className="link">
							the Cloud Run console
						</a>{" "}
						says.
					</Prose>
				</Panel>
			</Pair>
		</Page>
	);
}
