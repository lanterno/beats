/**
 * The operator's own records: the audit (editable by nobody, kept four
 * years) and the job queue, erasures first. Both empty until steps 3 and 4
 * write them — the pages exist so the first command lands somewhere visible.
 */

import { useQuery } from "@tanstack/react-query";
import { get } from "@/shared/api/client";
import { Failed, Loading, Section, Table } from "@/shared/ui";
import { CommandForm } from "@/shared/ui/CommandForm";

type Row = Record<string, unknown>;

function cells(row: Row, keys: string[]) {
	return keys.map((k) => {
		const v = row[k];
		return v === undefined || v === null ? "—" : String(v);
	});
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
		<>
			<Section title="Jobs — erasures first, each inside its window">
				{jobs.error ? <Failed error={jobs.error} /> : null}
				{jobs.data ? (
					<Table
						head={["Queued", "Command", "Subject", "Runs after", "State", ""]}
						rows={jobs.data.map((r) => [
							...cells(r, ["queued_at", "command", "subject_id", "run_after", "state"]),
							r.state === "queued" ? (
								<CommandForm
									key={`cancel-${r.id}`}
									name="job.cancel"
									label="Cancel"
									args={{ job_id: r.id }}
									invalidates={["operator-jobs", "attention"]}
								/>
							) : null,
						])}
					/>
				) : (
					<Loading />
				)}
			</Section>
			<Section title="Retention purge, platform-wide">
				<CommandForm
					name="retention.purge"
					label="Queue the purge for every organisation"
					args={{ organisation_id: null }}
					confirmHint='type "all"'
					invalidates={["operator-jobs"]}
				/>
				<p className="px-3 pb-3 text-xs text-neutral-500">
					Never scheduled, by decision: PRIVACY.md and the DPA promise an operator runs it. A
					whole-platform purge also trims the operator audit at its four-year retention.
				</p>
			</Section>
			<Section title="Operator audit">
				{audit.error ? <Failed error={audit.error} /> : null}
				{audit.data ? (
					<Table
						head={["When", "Command", "Operator", "Subject"]}
						rows={audit.data.map((r) => cells(r, ["at", "command", "operator_sub", "subject_id"]))}
					/>
				) : (
					<Loading />
				)}
			</Section>
		</>
	);
}
