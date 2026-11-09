/**
 * Jobs and windows: the irreversible work waiting out its window, where a
 * mistake is caught before it runs (docs/backoffice.md § Jobs). Erasures and
 * deletions sit here for days on purpose — this page is that purpose, so it
 * is a page of its own rather than a panel under compliance.
 *
 * What the mock shows and this does not: a history of each try, and a "run
 * it again" button. A job document keeps a count and the last error, not a
 * line per attempt, and no route re-runs a failed job — three attempts is
 * terminal, and the way back is to queue the command again.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { get } from "@/shared/api/client";
import { minuteOf } from "@/shared/lib/format";
import { Chip, day, Empty, Failed, Id, Loading, Page, Panel, Table } from "@/shared/ui";
import { CommandForm } from "@/shared/ui/CommandForm";

type Row = Record<string, unknown>;

const text = (value: unknown): string =>
	value === undefined || value === null ? "—" : String(value);

/**
 * The states a job document carries. "Waiting" is what `queued` means to a
 * person reading the page: it is in the window, not in a backlog.
 */
const STATES = [
	{ id: "all", label: "All" },
	{ id: "failed", label: "Failed" },
	{ id: "queued", label: "Waiting" },
	{ id: "running", label: "Running" },
	{ id: "done", label: "Done" },
	{ id: "cancelled", label: "Cancelled" },
] as const;

/** Three attempts and an entry is failed (`MAX_ATTEMPTS`, operator_jobs.py). */
const MAX_ATTEMPTS = 3;

type StateId = (typeof STATES)[number]["id"];

export function stateOf(row: Row): string {
	return typeof row.state === "string" ? row.state : "";
}

/** Rows in one state, or every row for "all". */
export function inState(rows: Row[], state: StateId): Row[] {
	return state === "all" ? rows : rows.filter((row) => stateOf(row) === state);
}

function JobState({ state }: { state: unknown }) {
	if (state === "failed") return <Chip tone="owed">Failed</Chip>;
	if (state === "done") return <Chip tone="good">Done</Chip>;
	if (state === "queued") return <Chip tone="owed">Waiting</Chip>;
	const name = text(state);
	return <Chip>{name.charAt(0).toUpperCase() + name.slice(1)}</Chip>;
}

/** "0 of 3", and the last error under a job that has one. */
function Tries({ row }: { row: Row }) {
	const attempts = typeof row.attempts === "number" ? row.attempts : 0;
	const error = typeof row.error === "string" && row.error ? row.error : null;
	return (
		<>
			<span className="whitespace-nowrap">
				{attempts} of {MAX_ATTEMPTS}
			</span>
			{error ? <span className="block text-[13px] text-ink-muted">{error}</span> : null}
		</>
	);
}

/** The sentence at the top: what, if anything, this page is asking for. */
export function jobsHeadline(rows: Row[]): string {
	const failed = inState(rows, "failed").length;
	const waiting = inState(rows, "queued").length;
	if (failed > 0 && waiting > 0) {
		return `${failed === 1 ? "One job has" : `${failed} jobs have`} failed and ${
			failed === 1 ? "needs" : "need"
		} you. ${waiting === 1 ? "One is" : `${waiting} are`} waiting out a window.`;
	}
	if (failed > 0) {
		return `${failed === 1 ? "One job has" : `${failed} jobs have`} failed and ${
			failed === 1 ? "needs" : "need"
		} you.`;
	}
	if (waiting > 0) {
		return `${waiting === 1 ? "One job is" : `${waiting} jobs are`} waiting out a window.`;
	}
	return "Nothing is waiting, and nothing has failed.";
}

export function Jobs() {
	const [state, setState] = useState<StateId>("all");
	const jobs = useQuery({
		queryKey: ["operator-jobs"],
		queryFn: () => get<Row[]>("/api/operator/jobs"),
	});

	if (jobs.error) return <Failed error={jobs.error} onRetry={() => jobs.refetch()} />;
	if (!jobs.data) return <Loading />;

	const rows = inState(jobs.data, state);
	return (
		<Page
			title={jobsHeadline(jobs.data)}
			lead="Anything that cannot be undone waits here before it runs, so a mistake can still be caught. The rules are checked again when it runs, not only when it was queued. Times are UTC."
		>
			<Panel raised>
				<div className="flex flex-wrap gap-1 px-6 pt-4 pb-1">
					{STATES.map(({ id, label }) => {
						const n = inState(jobs.data, id).length;
						return (
							<button
								key={id}
								type="button"
								aria-pressed={state === id}
								onClick={() => setState(id)}
								className={`inline-flex h-9 items-center gap-1.5 rounded-full px-3.5 text-[14px] ${
									state === id ? "bg-wash-strong font-bold" : "hover:bg-wash"
								}`}
							>
								{label}
								<span className="font-heading text-[13px] text-ink-muted">{n}</span>
							</button>
						);
					})}
				</div>
				<Table
					head={[day("Queued"), "Command", "Subject", day("Runs after"), "State", "Tries", ""]}
					rows={rows.map((r) => [
						minuteOf(r.queued_at),
						text(r.command),
						<Id key="subject">{text(r.subject_id)}</Id>,
						minuteOf(r.run_after),
						<JobState key="state" state={r.state} />,
						<Tries key="tries" row={r} />,
						r.state === "queued" ? (
							<CommandForm
								key={`cancel-${r.id}`}
								inline
								name="job.cancel"
								label={`Cancel ${text(r.command)} for ${text(r.subject_id)}`}
								action="Cancel"
								args={{ job_id: r.id }}
								invalidates={["operator-jobs", "attention"]}
							/>
						) : null,
					])}
					empty={
						state === "all" ? (
							<Empty title="Nothing is queued.">
								An erasure or a deletion waits here until its window ends.
							</Empty>
						) : (
							<Empty
								title={`No job is ${STATES.find((s) => s.id === state)?.label.toLowerCase()}.`}
							/>
						)
					}
				/>
			</Panel>
			<Panel
				title="How a window ends"
				note="The job runner drains the queue on a 15-minute tick, finding nothing due on almost every run."
			>
				<ul className="list-disc px-6 pb-5 pl-11 text-[15px] leading-relaxed">
					<li>
						A queued job can be cancelled until it runs. Cancelling an erasure also lifts the
						suspension that queueing it put on the account.
					</li>
					<li>
						A job's rules are checked when it runs: a deletion whose organisation gained an owner
						while it waited is refused then.
					</li>
					<li>
						A job that throws goes back in the queue and is tried again on the next tick. After
						three attempts it is <strong>failed</strong> and stops there, logged at{" "}
						<code>ERROR</code>, which pages the owner. Nothing re-runs it: queue the command again
						once you know why it failed.
					</li>
				</ul>
			</Panel>
		</Page>
	);
}
