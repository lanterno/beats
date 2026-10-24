/**
 * Report — what a client sees at `/r/:token` (docs/billing.md, phase 1c).
 *
 * The one page in the SPA outside `ProtectedRoute` that shows anyone's
 * data, and the only one a reader with no account ever opens. It is
 * deliberately plain: no `Layout`, no sidebar, no nav, no sign-in prompt.
 * There is nothing here for a reader to navigate to, and an invitation to
 * make an account would be the wrong thing to put in front of someone who
 * was sent an invoice's backing.
 *
 * Every figure is the API's, as everywhere else in billing: the page adds
 * nothing up and prices nothing. What it shows is decided by the link, not
 * by this component — with amounts hidden, the money fields simply are not
 * in the response.
 */

import { useParams } from "react-router";
import type { Report as ReportData } from "@/entities/billing";
import { useReport } from "@/entities/billing";
import {
	formatDateShort,
	formatMoney,
	formatRate,
	hoursText,
	parseIsoDate,
	parseUtcIso,
} from "@/shared/lib";
import { Panel, SkyBackdrop } from "@/shared/ui";

const TH =
	"py-1.5 font-body text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground";

function shortDay(iso: string): string {
	const d = parseIsoDate(iso);
	return d ? formatDateShort(d) : iso;
}

/** "Oct 1 – Oct 31", or the one day. */
function range(first: string, last: string): string {
	return first === last ? shortDay(first) : `${shortDay(first)} – ${shortDay(last)}`;
}

/** "Thu Oct 2". */
function entryDay(iso: string): string {
	const d = parseIsoDate(iso);
	return d ? `${d.toLocaleDateString("en-US", { weekday: "short" })} ${formatDateShort(d)}` : iso;
}

/**
 * "09:00", in the reader's own zone.
 *
 * The *days* are the owner's — the API bucketed them in the zone frozen on
 * the link, because those are the days they invoice on — but the clock on
 * a row is just a time, and showing it in the reader's zone is the least
 * surprising thing for them. A row can therefore read 23:00 under a day
 * that is not the reader's, which is correct: the work was done on the
 * owner's Thursday.
 */
function clock(timestamp: string): string {
	const d = parseUtcIso(timestamp);
	return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function Shell({ children }: { children: React.ReactNode }) {
	return (
		<>
			<SkyBackdrop />
			<main className="on-sky min-h-screen px-4 py-10 sm:py-16">
				<div className="mx-auto w-full max-w-3xl">{children}</div>
			</main>
		</>
	);
}

function ReportBody({ report }: { report: ReportData }) {
	const { currency, minorUnits } = report;
	// Both arrive together, and both are null on a link that hides amounts,
	// in which case no money figure is in the response to format.
	const priced = currency !== undefined && minorUnits !== undefined;
	const amount = (minor: number) => (priced ? formatMoney(minor, currency, minorUnits) : "—");
	const rate = (minor: number) => (priced ? formatRate(minor, currency, minorUnits) : "—");

	return (
		<>
			<header className="px-2">
				<h1 className="font-heading text-3xl font-extrabold tracking-[-0.02em] text-foreground">
					{report.clientName}
				</h1>
				<p className="mt-1 text-[13px] font-medium text-muted-foreground">
					{range(report.first, report.last)}
				</p>
			</header>

			<Panel role="region" aria-label="Total" padding="px-6 py-[22px]" className="mt-5">
				<p className="font-mono text-[22px] font-bold text-foreground">
					{hoursText(report.billableHours)}{" "}
					<span className="font-body text-[15px] font-medium text-muted-foreground">billable</span>
					{report.amountMinor !== undefined && <> · {amount(report.amountMinor)}</>}
				</p>
				{report.unpricedHours !== undefined && report.unpricedHours > 0 && (
					<p className="mt-1.5 text-[12.5px] font-medium text-muted-foreground">
						{hoursText(report.unpricedHours)} of that has no rate, so no amount.
					</p>
				)}
			</Panel>

			{report.lines.length > 0 && (
				<Panel role="region" aria-label="Work" padding="px-6 py-[22px]" className="mt-4">
					<table className="w-full text-[12.5px]">
						<thead>
							<tr className="text-left border-b border-border">
								<th className={TH}>Project</th>
								<th className={TH}>Days</th>
								<th className={`${TH} text-right`}>Hours</th>
								{report.showAmounts && <th className={`${TH} text-right`}>Rate</th>}
								{report.showAmounts && <th className={`${TH} text-right`}>Amount</th>}
							</tr>
						</thead>
						<tbody>
							{report.lines.map((line) => (
								<tr
									key={`${line.projectName}-${line.first}-${line.rateMinor ?? "none"}`}
									className="border-b border-border last:border-b-0"
								>
									<td className="py-2 font-medium text-foreground">{line.projectName}</td>
									<td className="py-2 text-muted-foreground whitespace-nowrap">
										{range(line.first, line.last)}
									</td>
									<td className="py-2 text-right font-mono font-bold text-foreground">
										{hoursText(line.hours)}
									</td>
									{report.showAmounts && (
										<td className="py-2 text-right font-mono text-muted-foreground whitespace-nowrap">
											{line.rateMinor !== undefined ? rate(line.rateMinor) : "—"}
										</td>
									)}
									{report.showAmounts && (
										<td className="py-2 text-right font-mono font-bold text-foreground whitespace-nowrap">
											{line.amountMinor !== undefined ? amount(line.amountMinor) : "—"}
										</td>
									)}
								</tr>
							))}
						</tbody>
					</table>
				</Panel>
			)}

			{report.entries.length > 0 && (
				<Panel role="region" aria-label="Entries" padding="px-6 py-[22px]" className="mt-4">
					<h2 className="font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
						Entries ({report.entries.length})
					</h2>
					<ul className="mt-1.5 flex flex-col">
						{report.entries.map((entry) => (
							<li
								key={`${entry.start}-${entry.end}`}
								className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 items-center py-2 border-t border-border text-[12.5px]"
							>
								<span className="font-mono font-bold text-foreground whitespace-nowrap">
									{entryDay(entry.day)} · {clock(entry.start)} → {clock(entry.end)}
								</span>
								<span className="font-mono text-muted-foreground">{hoursText(entry.hours)}</span>
							</li>
						))}
					</ul>
				</Panel>
			)}

			{report.lines.length === 0 && (
				<Panel padding="px-6 py-[22px]" className="mt-4">
					<p className="text-[12.5px] font-medium text-muted-foreground">
						No billable work in this range.
					</p>
				</Panel>
			)}
		</>
	);
}

export default function Report() {
	const { token } = useParams<{ token: string }>();
	const { data: report, isLoading, isError } = useReport(token ?? "");

	if (isLoading) {
		return (
			<Shell>
				<Panel padding="px-6 py-[22px]">
					<p className="text-[13px] font-medium text-muted-foreground">Loading…</p>
				</Panel>
			</Shell>
		);
	}

	// One message for every way a link fails, because the API answers one
	// 404 for all of them: a reader must not learn from the difference
	// between a link that never existed and one revoked yesterday.
	if (isError || !report) {
		return (
			<Shell>
				<Panel padding="px-6 py-[22px]">
					<h1 className="font-heading text-xl font-extrabold text-foreground">
						This report link is no longer available
					</h1>
					<p className="mt-2 text-[13px] font-medium text-muted-foreground">
						It may have been revoked, or the address may be incomplete. Ask whoever sent it for a
						new one.
					</p>
				</Panel>
			</Shell>
		);
	}

	return (
		<Shell>
			<ReportBody report={report} />
		</Shell>
	);
}
