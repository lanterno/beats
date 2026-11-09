/**
 * The audit log: every command the runner executed, with what it changed.
 * Written by the runner and not by the handlers, so the one action anybody
 * cares about cannot be the one nobody logged (docs/backoffice.md §
 * Commands). Ids, never addresses — it outlives the account it names — and
 * kept four years.
 *
 * What the mock shows and this does not: a "why" and a reference per row,
 * and lookups among the rows. Neither is kept: a reason on a command and an
 * audit of each read are undecided records (roadmaps/backoffice.md § Not
 * decided), and a column of blanks would read as "nobody said why" rather
 * than "nobody is asked".
 */

import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { Link } from "react-router";
import { get } from "@/shared/api/client";
import { minuteOf } from "@/shared/lib/format";
import { day, Empty, Failed, Id, Loading, Page, Panel, Table, TextField } from "@/shared/ui";

type Row = Record<string, unknown>;

const text = (value: unknown): string =>
	value === undefined || value === null ? "—" : String(value);

/**
 * Rows whose subject or command contains `needle`, matched without case.
 *
 * A filter over rows already on the page, never a query: a search the server
 * answers over the whole audit would be a way to ask "what has been done to
 * this address", and the address is not in here to ask with. The exact
 * account id is what an operator has in hand, and it matches whole.
 */
export function matching(rows: Row[], needle: string): Row[] {
	const wanted = needle.trim().toLowerCase();
	if (!wanted) return rows;
	return rows.filter((row) =>
		[row.subject_id, row.command].some(
			(field) => typeof field === "string" && field.toLowerCase().includes(wanted),
		),
	);
}

/** What a command changed, as the runner recorded it on either side. */
function Change({ row }: { row: Row }) {
	const shown = (value: unknown): ReactNode => {
		if (value === undefined || value === null) return <span className="text-ink-muted">—</span>;
		if (typeof value === "object" && Object.keys(value as object).length === 0) {
			return <span className="text-ink-muted">nothing</span>;
		}
		return <code className="text-[13px] break-words">{JSON.stringify(value)}</code>;
	};
	return (
		<div className="flex flex-col gap-0.5">
			<span>
				<span className="text-ink-muted">Before </span>
				{shown(row.before)}
			</span>
			<span>
				<span className="text-ink-muted">After </span>
				{shown(row.after)}
			</span>
		</div>
	);
}

/** A document id, and so a row with a page of its own to go to. */
const IDENTIFIER = /^[0-9a-f]{24}$/;

/** The pages for the two kinds of subject that have one. A purge's subject
 * is the word `all` and a cancel's is a job, so neither links. */
const PAGE: Record<string, string> = { account: "/accounts", organisation: "/organisations" };

function Subject({ row }: { row: Row }) {
	const id = text(row.subject_id);
	const page = typeof row.subject_kind === "string" ? PAGE[row.subject_kind] : undefined;
	if (page && IDENTIFIER.test(id)) {
		return (
			<Link to={`${page}/${id}`} className="link">
				<Id>{id}</Id>
			</Link>
		);
	}
	return <Id>{id}</Id>;
}

export function Audit() {
	const [needle, setNeedle] = useState("");
	const audit = useQuery({
		queryKey: ["operator-audit"],
		queryFn: () => get<Row[]>("/api/operator/audit"),
	});

	if (audit.error) return <Failed error={audit.error} onRetry={() => audit.refetch()} />;
	if (!audit.data) return <Loading />;

	const rows = matching(audit.data, needle);
	return (
		<Page
			title="Everything done from here, and who did it."
			lead="Written by the runner around each command, so nothing it ran is missing. It names whoever a command touched by id and never by address, it is kept four years, and nobody can edit it — you included. Times are UTC."
		>
			<Panel raised>
				<div className="px-6 pt-4">
					<TextField
						label="Filter by exact id or command"
						className="max-w-[26rem]"
						value={needle}
						onChange={(e) => setNeedle(e.target.value)}
						placeholder="u_… or account.suspend"
					/>
				</div>
				<Table
					head={[day("When"), "Operator", "Command", "Subject", "What changed"]}
					rows={rows.map((r) => [
						minuteOf(r.at),
						<span key="who" className="break-words">
							{text(r.operator_email)}
						</span>,
						text(r.command),
						<Subject key="subject" row={r} />,
						<Change key="change" row={r} />,
					])}
					empty={
						needle.trim() ? (
							<Empty title="Nothing here matches that.">
								The filter looks at the subject and the command of the rows already loaded.
							</Empty>
						) : (
							<Empty title="No commands have been run yet." />
						)
					}
				/>
			</Panel>
		</Page>
	);
}
