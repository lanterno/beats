/**
 * Who uses the product (docs/backoffice.md § The pages, decided
 * 2026-11-16): every account with its address, when it was created, the
 * day it was last seen, its state and how many projects and sessions it
 * holds — for the people who run and market it, who need to know who the
 * users are and whether they come back. Counts and dates only: what is in
 * a project or a session is the person's, and nothing here opens it.
 *
 * The lookup by exact address stays on its own page; this list is read
 * whole, sorted by the column the reader picks, and each row opens the
 * account's page. "Last seen" is a day, stamped at most once a day.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { get } from "@/shared/api/client";
import type { AccountsReport } from "@/shared/api/schema";
import { dayOf, whole } from "@/shared/lib/format";
import { peopleHeadline, type SortKey, sortRows } from "@/shared/lib/usage";
import { Chip, day, Empty, Failed, figure, Loading, Page, Panel, Table } from "@/shared/ui";

const SORTS: ReadonlyArray<{ id: SortKey; label: string }> = [
	{ id: "created", label: "Newest" },
	{ id: "seen", label: "Last seen" },
	{ id: "projects", label: "Most projects" },
	{ id: "sessions", label: "Most sessions" },
];

function Tile({ label, value }: { label: string; value: string }) {
	return (
		<Panel className="flex flex-col gap-1.5 px-5 py-4">
			<p className="text-[13px] text-ink-muted">{label}</p>
			<p className="font-heading text-[28px] leading-none font-extrabold">{value}</p>
		</Panel>
	);
}

export function People() {
	const [sort, setSort] = useState<SortKey>("created");
	const { data, error, refetch } = useQuery({
		queryKey: ["people"],
		queryFn: () => get<AccountsReport>("/api/operator/accounts"),
	});
	if (error) return <Failed error={error} onRetry={() => refetch()} />;
	if (!data) return <Loading />;

	const rows = sortRows(data.rows, sort);
	const shown =
		data.rows.length < data.total
			? `The newest ${whole(data.rows.length)} of ${whole(data.total)}.`
			: `All ${whole(data.total)}, newest first unless you sort them.`;
	return (
		<Page
			title={peopleHeadline(data.total, data.seen_last_30d)}
			lead="Every account, when it was made, when it was last here and how much it holds. What is inside a project or a session is the person's and is not on this page."
		>
			<section className="grid gap-[18px] sm:grid-cols-2 lg:grid-cols-4">
				<Tile label="Accounts" value={whole(data.total)} />
				<Tile label="New in the last 30 days" value={whole(data.created_last_30d)} />
				<Tile label="Here in the last 7 days" value={whole(data.seen_last_7d)} />
				<Tile label="Here in the last 30 days" value={whole(data.seen_last_30d)} />
			</section>
			<Panel raised title="Everyone" note={shown}>
				<fieldset className="flex flex-wrap gap-1 px-6 pb-2">
					<legend className="sr-only">Sort by</legend>
					{SORTS.map((s) => (
						<button
							key={s.id}
							type="button"
							aria-pressed={s.id === sort}
							onClick={() => setSort(s.id)}
							className={`h-9 rounded-full px-3.5 text-[14px] ${
								s.id === sort ? "bg-wash-strong font-bold" : "hover:bg-wash"
							}`}
						>
							{s.label}
						</button>
					))}
				</fieldset>
				<Table
					head={[
						"Account",
						day("Created"),
						day("Last seen"),
						figure("Projects"),
						figure("Sessions"),
						"State",
					]}
					rows={rows.map((r) => [
						<Link key={r.id} to={`/accounts/${r.id}`} className="link break-all">
							{r.email}
						</Link>,
						dayOf(r.created_at),
						dayOf(r.last_seen_on),
						whole(r.projects),
						whole(r.sessions),
						<Chip key="state" tone={r.suspended ? "owed" : "good"}>
							{r.suspended ? "Suspended" : "Active"}
						</Chip>,
					])}
					empty={<Empty title="Nobody has an account yet." />}
				/>
				{data.suspended > 0 ? (
					<p className="px-6 pb-5 text-[14px] text-ink-muted">
						{whole(data.suspended)} of them {data.suspended === 1 ? "is" : "are"} suspended.
					</p>
				) : null}
			</Panel>
		</Page>
	);
}
