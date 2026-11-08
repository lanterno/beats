/**
 * The irreversible work waiting out its window: erasures, deletions and
 * purges, each cancellable until the window ends. The runner looks every
 * fifteen minutes, so a job runs within a quarter of an hour of its window
 * closing; one that has failed three times stays here, marked, until
 * somebody looks.
 */

import { useQuery } from "@tanstack/react-query";
import { get } from "@/shared/api/client";
import { counted, minuteOf } from "@/shared/lib/format";
import { Chip, day, Empty, Failed, Id, Loading, Page, Panel, Table } from "@/shared/ui";
import { CommandForm } from "@/shared/ui/CommandForm";

type Row = Record<string, unknown>;

const text = (value: unknown): string =>
	value === undefined || value === null ? "—" : String(value);

function JobState({ state }: { state: unknown }) {
	if (state === "failed") return <Chip tone="owed">Failed</Chip>;
	if (state === "done") return <Chip tone="good">Done</Chip>;
	const name = text(state);
	return <Chip>{name.charAt(0).toUpperCase() + name.slice(1)}</Chip>;
}

function lead(rows: Row[] | undefined): string {
	if (!rows) return "The irreversible work, waiting out its window. Times are UTC.";
	const queued = rows.filter((r) => r.state === "queued").length;
	const failed = rows.filter((r) => r.state === "failed").length;
	const parts = [];
	if (queued > 0) parts.push(`${counted(queued, "job is", "jobs are")} waiting out a window`);
	if (failed > 0) parts.push(`${counted(failed, "has", "have")} failed and needs a look`);
	if (parts.length === 0) return "Nothing is waiting. Times are UTC.";
	return `${parts.join(", and ")}. Times are UTC.`;
}

export function Jobs() {
	const jobs = useQuery({
		queryKey: ["operator-jobs"],
		queryFn: () => get<Row[]>("/api/operator/jobs"),
	});

	return (
		<Page title="Jobs" lead={lead(jobs.data)}>
			<Panel
				raised
				note="Each one can be cancelled until its window ends. The runner looks every fifteen minutes, so a job runs within a quarter of an hour of that."
			>
				{jobs.error ? <Failed bare error={jobs.error} onRetry={() => jobs.refetch()} /> : null}
				{jobs.data ? (
					<Table
						head={[day("Queued"), "Command", "Subject", day("Runs after"), "State", ""]}
						rows={jobs.data.map((r) => [
							minuteOf(r.queued_at),
							text(r.command),
							<Id key="subject">{text(r.subject_id)}</Id>,
							minuteOf(r.run_after),
							<span key="state" title={r.error ? text(r.error) : undefined}>
								<JobState state={r.state} />
							</span>,
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
							<Empty title="Nothing is queued.">
								An erasure, a deletion or a purge waits here until its window ends.
							</Empty>
						}
					/>
				) : jobs.error ? null : (
					<Loading />
				)}
			</Panel>
		</Page>
	);
}
