/**
 * The work queue: every row behind an Attention count, each with a date and a
 * next step (roadmaps/backoffice.md, stage 1). There is nothing to tick off:
 * a row is the condition itself, so it leaves when the thing is dealt with and
 * comes back if it returns. Nothing here is stored, by the "not decided" list
 * in that roadmap.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { get } from "@/shared/api/client";
import type { QueueRow } from "@/shared/api/schema";
import { type Bucket, bucketOf, dueLabel, KINDS, queueHeadline } from "@/shared/lib/queue";
import { buttonClass, Chip, Empty, Failed, Id, Loading, Page, Panel, Prose } from "@/shared/ui";

const FILTERS: Array<{ id: Bucket | "all"; label: string }> = [
	{ id: "all", label: "All" },
	{ id: "overdue", label: "Overdue" },
	{ id: "today", label: "Today" },
	{ id: "later", label: "Later" },
];

const keyOf = (row: QueueRow) => `${row.kind}:${row.subject_id}`;

export function Queue() {
	const [filter, setFilter] = useState<Bucket | "all">("all");
	const [picked, setPicked] = useState<string | null>(null);
	const queue = useQuery({
		queryKey: ["operator-queue"],
		queryFn: () => get<QueueRow[]>("/api/operator/queue"),
	});
	if (queue.error) return <Failed error={queue.error} onRetry={() => queue.refetch()} />;
	if (!queue.data) return <Loading />;

	const now = new Date();
	const rows = queue.data;
	const shown = rows.filter((row) => filter === "all" || bucketOf(row, now) === filter);
	const selected = shown.find((row) => keyOf(row) === picked) ?? shown[0] ?? null;

	return (
		<Page
			title={queueHeadline(rows, now)}
			lead="Everything here needs you, and each one has a date and a next step. What only needs watching stays on the page it belongs to."
		>
			<div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
				<Panel raised>
					<div className="flex flex-wrap gap-1 px-6 pt-4 pb-1">
						{FILTERS.map(({ id, label }) => {
							const n =
								id === "all" ? rows.length : rows.filter((r) => bucketOf(r, now) === id).length;
							return (
								<button
									key={id}
									type="button"
									aria-pressed={filter === id}
									onClick={() => setFilter(id)}
									className={`inline-flex h-9 items-center gap-1.5 rounded-full px-3.5 text-[14px] ${
										filter === id ? "bg-wash-strong font-bold" : "hover:bg-wash"
									}`}
								>
									{label} <span className="font-heading">{n}</span>
								</button>
							);
						})}
					</div>
					{shown.length === 0 ? (
						<Empty title="Nothing here needs you.">
							Failed jobs, ownerless organisations and caps that are close land in this list when
							they happen.
						</Empty>
					) : (
						<ul className="px-3 pb-3">
							{shown.map((row) => {
								const kind = KINDS[row.kind];
								const on = selected !== null && keyOf(row) === keyOf(selected);
								return (
									<li key={keyOf(row)}>
										<button
											type="button"
											aria-pressed={on}
											onClick={() => setPicked(keyOf(row))}
											className={`flex w-full flex-wrap items-center gap-x-3 gap-y-1 rounded-[var(--radius-tile)] px-3 py-2.5 text-left text-[14px] ${
												on ? "bg-wash-strong" : "hover:bg-wash"
											}`}
										>
											<span className="min-w-[14rem] flex-1">{kind.title(row)}</span>
											<Chip>{kind.label}</Chip>
											<Chip tone={bucketOf(row, now) === "overdue" ? "owed" : "quiet"}>
												{dueLabel(row, now)}
											</Chip>
										</button>
									</li>
								);
							})}
						</ul>
					)}
				</Panel>
				{selected ? (
					<Panel title={KINDS[selected.kind].title(selected)}>
						<div className="flex flex-col gap-3 px-6 pb-5">
							<Prose>{KINDS[selected.kind].why}</Prose>
							<p className="text-[14px]">
								<span className="text-ink-muted">Subject </span>
								<Id>{selected.subject_id}</Id>
							</p>
							<Link to={KINDS[selected.kind].to(selected)} className={buttonClass("primary")}>
								{KINDS[selected.kind].next}
							</Link>
							<Link to={`/runbooks/${KINDS[selected.kind].runbook}`} className="link text-[14px]">
								Read the runbook
							</Link>
							<p className="text-[13px] text-ink-muted">
								There is nothing here to tick off. A row is the condition, not a note about it, so
								it leaves this list when the thing itself is dealt with.
							</p>
						</div>
					</Panel>
				) : null}
			</div>
		</Page>
	);
}
