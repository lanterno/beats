/**
 * ClientsOverview — the month at a glance, and the one click to any client.
 *
 * One row per client the month names: its hours, its amount and the state of
 * its budgets, with the name a link to that client's panel further down
 * (`clientSectionId`, and `scroll-mt-*` on the panel so the page bar does not
 * cover it). Before this, finding the third client meant scrolling past the
 * first two; now the list is the index to them.
 *
 * Every figure is the one `/api/billing/month` already returned for that
 * client — the same figure its panel prints. The only thing worked out here
 * is which of a client's budget states to show, and that is
 * `billingBudgetState`, the shared pure function, read against the same
 * clock the panels use.
 */

import type { BillingBudgetState, BillingBudgetStatus, ClientBilling } from "@/entities/billing";
import { billingBudgetState } from "@/entities/billing";
import { formatMoney, hoursText } from "@/shared/lib";
import { Chip, type ChipTone } from "@/shared/ui";
import { clientSectionId } from "./anchors";

const TH =
	"py-1.5 px-2 font-body text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground";

/** Used up beats near beats under: the row says the worst of the client's budgets. */
const RANK: Record<BillingBudgetState, number> = { under: 0, near: 1, used_up: 2 };
const BUDGET_CHIP: Record<BillingBudgetState, { tone: ChipTone; word: string }> = {
	under: { tone: "ok", word: "On budget" },
	near: { tone: "warn", word: "Near limit" },
	used_up: { tone: "bad", word: "Used up" },
};

function worstState(
	budgets: readonly BillingBudgetStatus[],
	now: number,
): BillingBudgetState | undefined {
	let worst: BillingBudgetState | undefined;
	for (const budget of budgets) {
		if (!budget.active || budget.upcoming) continue;
		const state = billingBudgetState(budget, now);
		if (!worst || RANK[state] > RANK[worst]) worst = state;
	}
	return worst;
}

export function ClientsOverview({
	clients,
	budgets,
	now,
	monthName,
}: {
	clients: readonly ClientBilling[];
	/** Every client's budgets, read as of today; absent in a month already over. */
	budgets?: readonly BillingBudgetStatus[];
	now: number;
	/** "October". */
	monthName: string;
}) {
	return (
		<section
			// The panel's own surface, so the figures are not read off the sky.
			className="rounded-[1.625rem] bg-card shadow-soft px-4 py-3"
			aria-label={`Clients in ${monthName}`}
		>
			<table className="w-full border-collapse text-[12.5px]">
				<caption className="sr-only">
					Every client with a panel below, and what {monthName} comes to for each
				</caption>
				<thead>
					<tr className="text-left">
						<th scope="col" className={TH}>
							Client
						</th>
						<th scope="col" className={TH}>
							State
						</th>
						<th scope="col" className={`${TH} text-right`}>
							Hours
						</th>
						<th scope="col" className={`${TH} text-right`}>
							Amount
						</th>
					</tr>
				</thead>
				<tbody>
					{clients.map((client) => {
						const state = worstState(
							(budgets ?? []).filter((b) => b.clientId === client.clientId),
							now,
						);
						const priced = client.lines.some((line) => line.amountMinor !== undefined);
						return (
							<tr key={client.clientId} className="border-t border-border align-middle">
								<td className="px-2 py-2">
									<a
										href={`#${clientSectionId(client.clientId)}`}
										className="font-bold text-accent-ink hover:underline underline-offset-[3px] rounded-full focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
									>
										{client.name}
									</a>
								</td>
								<td className="px-2 py-2">
									<span className="inline-flex items-center gap-1.5 flex-wrap">
										{client.archived && <Chip tone="wait">Archived</Chip>}
										{state && <Chip tone={BUDGET_CHIP[state].tone}>{BUDGET_CHIP[state].word}</Chip>}
										{client.running && <Chip tone="warn">Timer running</Chip>}
										{!client.archived && !state && !client.running && (
											<span className="text-muted-foreground font-medium">—</span>
										)}
									</span>
								</td>
								<td className="px-2 py-2 text-right font-mono font-bold text-foreground whitespace-nowrap">
									{hoursText(client.billableHours)}
								</td>
								<td className="px-2 py-2 text-right font-mono font-bold text-foreground whitespace-nowrap">
									{priced
										? formatMoney(client.amountMinor, client.currency, client.minorUnits)
										: "—"}
								</td>
							</tr>
						);
					})}
				</tbody>
			</table>
		</section>
	);
}
