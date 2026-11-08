/**
 * The three pieces every page is made of: a titled section, a plain dense
 * table, and a key–value list. Deliberately not ui/'s Panel-and-sky.
 */

import type { ReactNode } from "react";

export function Section({ title, children }: { title: string; children: ReactNode }) {
	return (
		<section className="mb-8">
			<h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500 mb-2">
				{title}
			</h2>
			<div className="bg-white border border-neutral-200 rounded">{children}</div>
		</section>
	);
}

export function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
	if (rows.length === 0) {
		return <p className="p-3 text-sm text-neutral-500">Nothing here.</p>;
	}
	return (
		<table className="w-full text-sm">
			<thead>
				<tr className="border-b border-neutral-200 text-left text-neutral-500">
					{head.map((h) => (
						<th key={h} className="px-3 py-2 font-medium">
							{h}
						</th>
					))}
				</tr>
			</thead>
			<tbody>
				{rows.map((cells, i) => (
					// biome-ignore lint/suspicious/noArrayIndexKey: rows are read-only renderings of API lists with no stable id of their own
					<tr key={i} className="border-b border-neutral-100 last:border-0">
						{cells.map((cell, j) => (
							// biome-ignore lint/suspicious/noArrayIndexKey: a cell's column is its identity
							<td key={j} className="px-3 py-1.5 align-top">
								{cell}
							</td>
						))}
					</tr>
				))}
			</tbody>
		</table>
	);
}

export function Facts({ items }: { items: Array<[string, ReactNode]> }) {
	return (
		<dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1 p-3 text-sm">
			{items.map(([label, value]) => (
				<div key={label} className="contents">
					<dt className="text-neutral-500">{label}</dt>
					<dd>{value}</dd>
				</div>
			))}
		</dl>
	);
}

export function Loading() {
	return <p className="p-3 text-sm text-neutral-500">Loading…</p>;
}

export function Failed({ error }: { error: unknown }) {
	const message = error instanceof Error ? error.message : "Request failed";
	return <p className="p-3 text-sm text-red-700">{message}</p>;
}
