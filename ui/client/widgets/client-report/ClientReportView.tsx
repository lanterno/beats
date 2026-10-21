/**
 * ClientReportView — a public report as the client reads it: one panel, a
 * document rather than the app. The report page draws it from
 * `POST /api/public/reports`, and the share dialog's preview from the same
 * answer before the link exists, so what the freelancer checks is what the
 * client sees (docs/billing.md, *Report links (phase 1c)*).
 *
 * Every figure is the API's. A month is a section, its lines read as the
 * invoice does (`30.00 h × €85.00/h = €2,550.00`, or project and hours on a
 * link without amounts), and its day rows are folded on screen and open in
 * print. Nothing here names the sender, the time zone or the link.
 *
 * Its imports are the report page's fence (biome.json): single modules of
 * `shared/lib` and `shared/ui`, never their barrels, which reach the session
 * and the API client.
 */

import { ChevronRight } from "lucide-react";
import { Fragment, type ReactNode, useId, useState } from "react";
import { APP_NAME } from "@/shared/config";
import { cn } from "@/shared/lib/cn";
import type {
	PricedLine,
	PublicReport,
	ReportDay,
	ReportMoney,
	ReportMonth,
} from "@/shared/report";
import { Panel } from "@/shared/ui/panel";
import {
	amountText,
	betweenText,
	currencyName,
	dateText,
	dayText,
	hoursFixed,
	lineArithmetic,
	monthHeading,
	rangeText,
	runText,
} from "./figures";

export interface ClientReportViewProps {
	report: PublicReport;
	/** The viewer's today, for "Figures as they stand on". */
	today: Date;
	/** Beside "Prepared with": the page's print button. The preview has none. */
	action?: ReactNode;
}

const LABEL = "font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground";
const TH =
	"py-1.5 px-1 font-body text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground";
const NOTE = "text-[12.5px] text-muted-foreground font-medium";

/** "15–30 September 2026 (part of the month)", or "October 2026". */
function headingOf(month: ReportMonth): string {
	return month.whole_month
		? monthHeading(month.month)
		: `${rangeText(month.first, month.last)} (part of the month)`;
}

function PricedLines({
	lines,
	money,
	caption,
}: {
	lines: PricedLine[];
	money: ReportMoney;
	caption: string;
}) {
	return (
		<table className="mt-2 w-full text-[13px] border-collapse">
			<caption className="sr-only">{caption}</caption>
			<thead>
				<tr className="text-left">
					<th scope="col" className={TH}>
						Project
					</th>
					{/* Under the project's name on a phone. */}
					<th scope="col" className={cn(TH, "hidden sm:table-cell")}>
						Days
					</th>
					<th scope="col" className={cn(TH, "text-right")}>
						Hours and amount
					</th>
				</tr>
			</thead>
			<tbody>
				{lines.map((line, i) => (
					<tr key={i} className="border-t border-border align-baseline break-inside-avoid">
						<td className="px-1 py-2 font-bold text-foreground min-w-0 break-words">
							{line.project_name}
							<span className="sm:hidden block font-mono text-[11px] text-muted-foreground">
								{runText(line.first, line.last)}
							</span>
						</td>
						<td className="px-1 py-2 whitespace-nowrap font-mono text-muted-foreground font-bold hidden sm:table-cell">
							{runText(line.first, line.last)}
						</td>
						<td className="px-1 py-2 text-right font-mono font-bold text-foreground">
							{/* Two pieces that wrap apart on a phone: "30.00 h × €85.00/h" and "= €2,550.00". */}
							{lineArithmetic(line, money).map((piece, i) => (
								<Fragment key={piece}>
									{i > 0 && " "}
									<span className="inline-block whitespace-nowrap">{piece}</span>
								</Fragment>
							))}
						</td>
					</tr>
				))}
			</tbody>
		</table>
	);
}

function HoursLines({
	lines,
	caption,
}: {
	lines: { project_name: string; hours: number }[];
	caption: string;
}) {
	return (
		<table className="mt-2 w-full text-[13px] border-collapse">
			<caption className="sr-only">{caption}</caption>
			<thead>
				<tr className="text-left">
					<th scope="col" className={TH}>
						Project
					</th>
					<th scope="col" className={cn(TH, "text-right")}>
						Hours
					</th>
				</tr>
			</thead>
			<tbody>
				{lines.map((line, i) => (
					<tr key={i} className="border-t border-border align-baseline break-inside-avoid">
						<td className="px-1 py-2 font-bold text-foreground min-w-0 break-words">
							{line.project_name}
						</td>
						<td className="px-1 py-2 text-right font-mono font-bold text-foreground whitespace-nowrap">
							{hoursFixed(line.hours)} h
						</td>
					</tr>
				))}
			</tbody>
		</table>
	);
}

function DayRows({ days, heading }: { days: ReportDay[]; heading: string }) {
	const [open, setOpen] = useState(false);
	const id = useId();
	return (
		<div className="mt-2">
			<button
				type="button"
				aria-expanded={open}
				aria-controls={id}
				onClick={() => setOpen((was) => !was)}
				className={cn(
					LABEL,
					"inline-flex items-center gap-1 rounded-full hover:text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring print:hidden",
				)}
			>
				<ChevronRight
					className={cn("w-3 h-3 transition-transform", open && "rotate-90")}
					aria-hidden="true"
				/>
				Day by day
			</button>
			{/* Folded on screen, always open in print: a printed page stands alone. */}
			<div id={id} className={open ? "block" : "hidden print:block"}>
				<table className="mt-1 w-full text-[12.5px] border-collapse">
					<caption className="sr-only">{heading}, day by day</caption>
					<thead>
						<tr className="text-left">
							<th scope="col" className={TH}>
								Day
							</th>
							<th scope="col" className={TH}>
								Project
							</th>
							<th scope="col" className={cn(TH, "text-right")}>
								Hours
							</th>
						</tr>
					</thead>
					<tbody>
						{days.map((day, i) => (
							<tr key={i} className="border-t border-border align-baseline break-inside-avoid">
								<td className="px-1 py-1.5 font-mono font-bold text-muted-foreground whitespace-nowrap">
									{dayText(day.day)}
								</td>
								<td className="px-1 py-1.5 font-bold text-foreground min-w-0 break-words">
									{day.project_name}
									{day.notes && day.notes.length > 0 && (
										<ul className="mt-0.5 font-medium text-muted-foreground">
											{day.notes.map((note, n) => (
												<li key={n}>{note}</li>
											))}
										</ul>
									)}
								</td>
								<td className="px-1 py-1.5 text-right font-mono font-bold text-foreground whitespace-nowrap">
									{hoursFixed(day.hours)} h
								</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>
		</div>
	);
}

function MonthSection({ month, money }: { month: ReportMonth; money?: ReportMoney }) {
	const heading = headingOf(month);
	const total =
		money && "amount_minor" in month
			? `${hoursFixed(month.billable_hours)} h · ${amountText(month.amount_minor, month.unpriced_hours, month.billable_hours, money)}`
			: `${hoursFixed(month.billable_hours)} h`;
	return (
		<section aria-label={heading} className="mt-6">
			<div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 break-inside-avoid break-after-avoid">
				<h2 className="font-heading text-[15px] font-extrabold text-foreground">{heading}</h2>
				<p className="font-mono text-[13px] font-bold text-foreground">{total}</p>
			</div>
			{month.lines.length === 0 ? (
				<p className={cn(NOTE, "mt-1.5")}>No billable hours in these days.</p>
			) : (
				<>
					{money && "amount_minor" in month ? (
						<PricedLines lines={month.lines} money={money} caption={`${heading}, by project`} />
					) : (
						<HoursLines lines={month.lines} caption={`${heading}, by project`} />
					)}
					{month.days.length > 0 && <DayRows days={month.days} heading={heading} />}
				</>
			)}
		</section>
	);
}

export function ClientReportView({ report, today, action }: ClientReportViewProps) {
	const money = "money" in report ? report.money : undefined;
	const empty = report.months.every((month) => month.lines.length === 0);
	const todayText = dateText(
		`${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`,
	);
	const rounding = money
		? `Each line is a run of days at one rate, rounded once: its hours to the hundredth of an hour, its amount to ${money.minor_units === 2 ? "the cent" : "the currency's smallest unit"}.`
		: "Each line is one project's billable hours in the month, as invoiced, to the hundredth of an hour.";

	return (
		<Panel padding="px-5 py-6 sm:px-8 sm:py-8" className="print:bg-transparent print:shadow-none">
			<header>
				<p className={LABEL}>Hours report</p>
				<h1 className="mt-1 font-heading text-2xl font-extrabold tracking-[-0.01em] text-foreground break-words">
					{report.client_name}
				</h1>
				<p className="mt-0.5 font-mono text-[13px] font-bold text-muted-foreground">
					{rangeText(report.first, report.last)}
				</p>
			</header>

			{empty ? (
				<p className="mt-5 text-[14px] font-medium text-foreground">
					No billable hours for {report.client_name} {betweenText(report.first, report.last)}.
				</p>
			) : (
				<>
					<div className="mt-5 print:border print:border-foreground/30 print:rounded-2xl print:px-3 print:py-2">
						<p className="font-mono text-lg font-bold text-foreground">
							{hoursFixed(report.billable_hours)}{" "}
							<span className="font-body font-medium">billable hours</span>
							{money && (
								<>
									{" · "}
									{amountText(
										money.amount_minor,
										money.unpriced_hours,
										report.billable_hours,
										money,
									)}
								</>
							)}
						</p>
						<p className={cn(NOTE, "mt-0.5")}>
							{money
								? `Amounts in ${currencyName(money.currency)} (${money.currency}), before tax. Billable hours only.`
								: "Hours only. Amounts are on your invoice."}
						</p>
					</div>
					{report.months.map((month) => (
						<MonthSection key={month.month} month={month} money={money} />
					))}
				</>
			)}

			<section aria-label="How these figures are worked out" className="mt-8 break-inside-avoid">
				<h2 className={LABEL}>How these figures are worked out</h2>
				<p className={cn(NOTE, "mt-1")}>
					{rounding} Every total is a sum of lines. A whole month here is the month as invoiced.
					Each day is rounded on its own; the totals are worked from exact times. Days are counted
					in the sender's time zone.
				</p>
			</section>

			<footer className="mt-5 break-inside-avoid">
				<p className={NOTE}>Figures as they stand on {todayText}.</p>
				<p className={cn(NOTE, "mt-1")}>
					This page records nothing about you. The server keeps an ordinary request log (address,
					browser, time), never the link.
				</p>
				<div className="mt-4 flex flex-wrap items-center justify-between gap-3">
					{action ?? <span />}
					<p className={NOTE}>Prepared with {APP_NAME}</p>
				</div>
			</footer>
		</Panel>
	);
}
