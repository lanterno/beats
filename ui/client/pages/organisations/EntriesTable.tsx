/**
 * EntriesTable — the finished entries an organisation holds, one row each:
 * the local day, start → end in the reader's own zone, the hours and the
 * note. The record page and the archive draw the same table, since both
 * show the same `RecordEntry` from the same read.
 */

import type { RecordEntry } from "@/entities/organisation";
import { formatDateOnly, formatTime, hoursText } from "@/shared/lib";

const TH =
	"py-1.5 pr-3 text-left font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground";
const TD = "py-1.5 pr-3 align-top text-[12.5px]";

export interface EntriesTableProps {
	entries: RecordEntry[];
	/** Names the table for a reader who lands on it: "Entries on Payroll for Ada". */
	label: string;
}

export function EntriesTable({ entries, label }: EntriesTableProps) {
	return (
		<div className="overflow-x-auto">
			<table className="w-full border-collapse" aria-label={label}>
				<thead>
					<tr className="border-b border-border">
						<th scope="col" className={TH}>
							Day
						</th>
						<th scope="col" className={TH}>
							Time
						</th>
						<th scope="col" className={`${TH} text-right`}>
							Hours
						</th>
						<th scope="col" className={TH}>
							Note
						</th>
					</tr>
				</thead>
				<tbody className="divide-y divide-border">
					{entries.map((entry) => (
						<tr key={entry.id}>
							<td className={`${TD} whitespace-nowrap font-medium text-foreground`}>
								{formatDateOnly(entry.day)}
							</td>
							<td className={`${TD} whitespace-nowrap font-mono text-foreground`}>
								{formatTime(entry.start)} → {formatTime(entry.end)}
							</td>
							<td className={`${TD} whitespace-nowrap font-mono text-right text-foreground`}>
								{hoursText(entry.hours)}
							</td>
							<td className={`${TD} text-muted-foreground`}>{entry.note ?? ""}</td>
						</tr>
					))}
				</tbody>
			</table>
		</div>
	);
}
