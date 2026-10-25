/**
 * MonthTotals — the mockup's `.statrow` at the top of the Clients page: the
 * month's amount per currency, the hours behind them, and how many clients
 * the month names.
 *
 * Every figure here is one the API already returned in `/api/billing/month`.
 * An amount is a `totals` entry read as it came — the SPA prices nothing and
 * never adds two currencies — and the hours are the same entries' hours,
 * added the way `summary.ts` adds them, as hundredths. Nothing is computed
 * that the sentence above does not already say; the tiles only make it
 * readable at a glance.
 */

import type { BillingMonth } from "@/entities/billing";
import { formatMoney, hoursText } from "@/shared/lib";
import { Panel } from "@/shared/ui";

/** The API's figures are hundredths; summing floats must not invent a third decimal. */
function sum(values: number[]): number {
	return Math.round(values.reduce((total, v) => total + v, 0) * 100) / 100;
}

function Tile({ label, figure, note }: { label: string; figure: string; note?: string }) {
	return (
		// `panel-tile`: in the sheet layout a tile keeps a surface as a wash.
		<Panel padding="px-5 py-4" className="panel-tile">
			<p className="font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
				{label}
			</p>
			<p className="mt-1 font-mono text-[26px] font-extrabold leading-none text-foreground">
				{figure}
			</p>
			{note && <p className="mt-1.5 text-[12px] font-medium text-muted-foreground">{note}</p>}
		</Panel>
	);
}

export function MonthTotals({
	report,
	current,
	monthName,
}: {
	report: BillingMonth;
	/** The month is still running, so every figure is "so far". */
	current: boolean;
	/** "October". */
	monthName: string;
}) {
	const priced = report.totals.filter((total) => total.amountMinor > 0);
	const billableHours = sum(report.totals.map((total) => total.billableHours));
	const unpriced = sum(report.totals.map((total) => total.unpricedHours));
	const billedClients = report.clients.filter((client) => client.billableHours > 0).length;
	const when = current ? `${monthName} so far` : monthName;

	return (
		<section
			aria-label="Month totals"
			className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(13rem,1fr))]"
		>
			{priced.map((total) => (
				<Tile
					key={total.currency}
					label={priced.length > 1 ? `Billable · ${total.currency}` : "Billable"}
					figure={formatMoney(total.amountMinor, total.currency, total.minorUnits)}
					note={`${hoursText(total.billableHours)} priced in ${total.currency}`}
				/>
			))}
			<Tile
				label="Hours billable"
				figure={hoursText(billableHours)}
				note={unpriced > 0 ? `${hoursText(unpriced)} with no rate` : when}
			/>
			<Tile
				label="Clients"
				figure={String(report.clients.length)}
				note={
					billedClients === report.clients.length
						? `${billedClients === 1 ? "the one" : "all"} with hours in ${monthName}`
						: `${billedClients} with hours in ${monthName}`
				}
			/>
		</section>
	);
}
