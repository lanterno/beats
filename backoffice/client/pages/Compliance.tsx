/**
 * The operator's own records: the audit (editable by nobody, kept four
 * years) and the job queue, erasures first — where every command the runner
 * executed shows, and where a queued window is waited out or cancelled.
 */

import { useQuery } from "@tanstack/react-query";
import { get } from "@/shared/api/client";
import { minuteOf } from "@/shared/lib/format";
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

export function Compliance() {
	const audit = useQuery({
		queryKey: ["operator-audit"],
		queryFn: () => get<Row[]>("/api/operator/audit"),
	});
	const jobs = useQuery({
		queryKey: ["operator-jobs"],
		queryFn: () => get<Row[]>("/api/operator/jobs"),
	});

	return (
		<Page
			title="Compliance"
			lead="Your own records: the work waiting out its window, and everything the back office has run. Times are UTC."
		>
			<Panel
				raised
				title="Jobs"
				note="Each one waits out its window, and can be cancelled until it ends."
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
							<JobState key="state" state={r.state} />,
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
								An erasure or a deletion waits here until its window ends.
							</Empty>
						}
					/>
				) : jobs.error ? null : (
					<Loading />
				)}
			</Panel>
			<Panel
				danger
				title="Retention purge, platform-wide"
				note="Never scheduled, by decision: PRIVACY.md and the DPA promise an operator runs it."
			>
				<CommandForm
					name="retention.purge"
					label="Purge every organisation"
					about="It also trims the operator audit at its four-year retention."
					action="Queue the purge"
					done="Queued. Cancel it from the jobs above."
					args={{ organisation_id: null }}
					confirmHint='Type "all" to confirm'
					invalidates={["operator-jobs"]}
				/>
			</Panel>
			<Panel
				title="Operator audit"
				note="Every command the back office has run. Nobody can edit it."
			>
				{audit.error ? <Failed bare error={audit.error} onRetry={() => audit.refetch()} /> : null}
				{audit.data ? (
					<Table
						head={[day("When"), "Command", "Operator", "Subject"]}
						rows={audit.data.map((r) => [
							minuteOf(r.at),
							text(r.command),
							<Id key="operator">{text(r.operator_sub)}</Id>,
							<Id key="subject">{text(r.subject_id)}</Id>,
						])}
						empty={<Empty title="No commands have been run yet." />}
					/>
				) : audit.error ? null : (
					<Loading />
				)}
			</Panel>
		</Page>
	);
}
