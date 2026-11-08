/**
 * The operator's own audit: every command the runner executed, with what
 * it changed, kept four years and editable by nobody. Ids, never
 * addresses — a row outlives the account it names.
 */

import { useQuery } from "@tanstack/react-query";
import { get } from "@/shared/api/client";
import { changes } from "@/shared/lib/changes";
import { counted, minuteOf } from "@/shared/lib/format";
import { day, Empty, Failed, Id, Loading, Page, Panel, Table } from "@/shared/ui";

type Row = Record<string, unknown>;

const text = (value: unknown): string =>
	value === undefined || value === null ? "—" : String(value);

const fields = (value: unknown): Record<string, unknown> | null =>
	value && typeof value === "object" ? (value as Record<string, unknown>) : null;

export function Audit() {
	const audit = useQuery({
		queryKey: ["operator-audit"],
		queryFn: () => get<Row[]>("/api/operator/audit"),
	});

	return (
		<Page
			title="Audit"
			lead={
				audit.data
					? `${counted(audit.data.length, "command", "commands")} on record, newest first. Kept four years, and nobody can edit it. Times are UTC.`
					: "Every command the back office has run. Times are UTC."
			}
		>
			<Panel raised>
				{audit.error ? <Failed bare error={audit.error} onRetry={() => audit.refetch()} /> : null}
				{audit.data ? (
					<Table
						head={[day("When"), "Command", "Operator", "Subject", "What changed"]}
						rows={audit.data.map((r) => {
							const changed = changes(fields(r.before), fields(r.after));
							return [
								minuteOf(r.at),
								text(r.command),
								<span key="operator" title={text(r.operator_sub)}>
									{text(r.operator_email)}
								</span>,
								<Id key="subject">{text(r.subject_id)}</Id>,
								changed.length > 0 ? (
									<ul key="changes" className="font-heading text-[13px] whitespace-nowrap">
										{changed.map((line) => (
											<li key={line}>{line}</li>
										))}
									</ul>
								) : (
									<span key="changes" className="text-ink-muted">
										Nothing
									</span>
								),
							];
						})}
						empty={<Empty title="No commands have been run yet." />}
					/>
				) : audit.error ? null : (
					<Loading />
				)}
			</Panel>
		</Page>
	);
}
