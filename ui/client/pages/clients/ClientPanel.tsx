/**
 * ClientPanel — one client's month on the Clients page: the name and the
 * rate in force today, what the month comes to, the lines it is made of,
 * and the entries behind them, each with its Billable pill.
 *
 * A line is a run of consecutive days of one project at one rate from one
 * source (docs/billing.md), so the table reads as an invoice would: hours
 * × rate = amount on every row, in the client's one currency, and the
 * figure above is their sum. A line with no rate at either level has no
 * amount, and says where to set one. Every figure is the API's; the pill
 * alone is worked out here (`entryBillable`), so a tap shows at once.
 *
 * In the current month the month's figure is followed by the client's
 * billing budgets (docs/billing.md, phase 1b): its own, then each of its
 * projects', each a sentence and a meter with a pencil that opens
 * `BillingBudgetDialog` for that scope. Without a budget of its own the
 * panel offers a quiet "Set a budget", and nothing more.
 */

import { ChevronRight, Pencil } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import type {
	BillingBudgetScope,
	BillingBudgetStatus,
	BillingEntry,
	ClientBilling,
	ProjectBilling,
} from "@/entities/billing";
import {
	BillableSwitch,
	BillingBudgetDialog,
	BillingBudgetRow,
	entryBillable,
	inForceOn,
} from "@/entities/billing";
import type { Client } from "@/entities/client";
import { useArchiveClient, useDeleteClient, useUnarchiveClient } from "@/entities/client";
import { describeError } from "@/shared/api";
import {
	cn,
	formatDateShort,
	formatMoney,
	formatRate,
	hoursText,
	parseIsoDate,
	parseUtcIso,
} from "@/shared/lib";
import { Button, Panel } from "@/shared/ui";

export interface ClientPanelProps {
	billing: ClientBilling;
	/** The client's record, for its rates and contact; absent until the clients load. */
	client?: Client;
	todayIso: string;
	tz: string;
	/** "October". */
	monthName: string;
	/** Every project's name by id, archived ones included, for the entries. */
	projectNames: ReadonlyMap<string, string>;
	projectBillings?: ReadonlyMap<string, ProjectBilling>;
	overrides?: ReadonlyMap<string, boolean>;
	/**
	 * The client's billing budgets, its own and its projects', read as of
	 * today: only in the current month, since a budget is never read
	 * against a month already over. Absent, the panel shows none.
	 */
	budgets?: readonly BillingBudgetStatus[];
	/** The budgets could not be read — an older API during a deploy. */
	budgetsFailed?: boolean;
	/** The clock a running timer's instants are read against. */
	now?: number;
	onEdit: () => void;
}

interface BudgetEditor {
	scope: BillingBudgetScope;
	scopeId: string;
	name: string;
	status?: BillingBudgetStatus;
	billingStartedOn?: string;
}

const LABEL = "font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground";
const LINKISH =
	"text-accent-ink text-[12.5px] font-bold hover:underline underline-offset-[3px] rounded-full disabled:opacity-40 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";
const OP =
	"grid place-items-center w-[22px] h-[22px] rounded-full text-muted-foreground hover:bg-sidebar-accent hover:text-foreground transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";
const TH =
	"py-1.5 font-body text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground";

function shortDay(iso: string): string {
	const d = parseIsoDate(iso);
	return d ? formatDateShort(d) : iso;
}

/** "Oct 1 – Oct 14", or the one day. */
function days(first: string, last: string): string {
	return first === last ? shortDay(first) : `${shortDay(first)} – ${shortDay(last)}`;
}

/** "Thu Oct 2", the local day the API bucketed the entry on. */
function entryDay(iso: string): string {
	const d = parseIsoDate(iso);
	return d ? `${d.toLocaleDateString("en-US", { weekday: "short" })} ${formatDateShort(d)}` : iso;
}

/** "09:00", in the browser's zone — the one the page sends the API. */
function clock(timestamp: string): string {
	const d = parseUtcIso(timestamp);
	return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** "€85.00/h since Jan 1, 2026", or that there is none. */
function rateToday(client: Client, todayIso: string): string {
	const rate = inForceOn(client.rates, todayIso);
	if (!rate) return "No default rate";
	const since = parseIsoDate(rate.effectiveFrom);
	const sinceText = since
		? `${formatDateShort(since)}${since.getFullYear() === Number(todayIso.slice(0, 4)) ? "" : `, ${since.getFullYear()}`}`
		: rate.effectiveFrom;
	return `${formatRate(rate.rateMinor, client.currency, client.minorUnits)} since ${sinceText}`;
}

/** The earliest term of these billings: when billing started. */
function earliestTerm(billings: readonly ProjectBilling[]): string | undefined {
	return billings.flatMap((b) => b.terms.map((term) => term.effectiveFrom)).sort()[0];
}

function EntryRow({
	entry,
	projectName,
	billing,
	overrides,
	tz,
}: {
	entry: BillingEntry;
	projectName: string;
	billing?: ProjectBilling;
	overrides?: ReadonlyMap<string, boolean>;
	tz: string;
}) {
	// The cache's marks first, so a tap shows before the month is read again.
	const shown =
		billing && overrides
			? entryBillable({ id: entry.beatId, startTime: entry.start }, billing, overrides, tz)
			: { billable: entry.billable, overridden: entry.overridden };
	const label = `${entryDay(entry.day)}, ${clock(entry.start)}, ${projectName}`;
	return (
		<li className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 items-center py-2 border-t border-border text-[12.5px]">
			<span className="min-w-0">
				<span className="font-mono font-bold text-foreground whitespace-nowrap">
					{entryDay(entry.day)} · {clock(entry.start)} → {clock(entry.end)}
				</span>
				<span className="block text-muted-foreground font-medium truncate">
					{projectName} · {hoursText(entry.hours)}
				</span>
			</span>
			<BillableSwitch
				beatId={entry.beatId}
				billable={shown.billable}
				overridden={shown.overridden}
				entryLabel={label}
			/>
		</li>
	);
}

export function ClientPanel({
	billing,
	client,
	todayIso,
	tz,
	monthName,
	projectNames,
	projectBillings,
	overrides,
	budgets,
	budgetsFailed = false,
	now = Date.now(),
	onEdit,
}: ClientPanelProps) {
	const archive = useArchiveClient();
	const unarchive = useUnarchiveClient();
	const remove = useDeleteClient();
	const [entriesOpen, setEntriesOpen] = useState(false);
	const [confirmingDelete, setConfirmingDelete] = useState(false);
	const [budgetEditor, setBudgetEditor] = useState<BudgetEditor | null>(null);

	const { currency, minorUnits } = billing;
	const money = (minor: number) => formatMoney(minor, currency, minorUnits);
	const billedProjects = projectBillings
		? [...projectBillings.values()].filter((b) => b.clientId === billing.clientId).length
		: undefined;
	const unpriced = new Map<string, { name: string; hours: number }>();
	for (const line of billing.lines) {
		if (line.rateMinor !== undefined) continue;
		const seen = unpriced.get(line.projectId);
		unpriced.set(line.projectId, {
			name: line.projectName,
			hours: (seen?.hours ?? 0) + line.hours,
		});
	}
	const nameOf = (projectId: string) =>
		projectNames.get(projectId) ??
		billing.lines.find((line) => line.projectId === projectId)?.projectName ??
		"A project";
	const pending = archive.isPending || unarchive.isPending || remove.isPending;

	const clientBillings = projectBillings
		? [...projectBillings.values()].filter((b) => b.clientId === billing.clientId)
		: [];
	const ownBudget = budgets?.find((b) => b.scope === "client");
	const projectBudgets = (budgets ?? []).filter((b) => b.scope === "project");
	const editClientBudget = () =>
		setBudgetEditor({
			scope: "client",
			scopeId: billing.clientId,
			name: billing.name,
			status: ownBudget,
			billingStartedOn: earliestTerm(clientBillings),
		});
	const editProjectBudget = (status: BillingBudgetStatus) =>
		setBudgetEditor({
			scope: "project",
			scopeId: status.scopeId,
			name: status.name,
			status,
			billingStartedOn: earliestTerm(clientBillings.filter((b) => b.projectId === status.scopeId)),
		});
	const pencil = (name: string, onClick: () => void) => (
		<button type="button" onClick={onClick} aria-label={`Edit ${name}'s budget`} className={OP}>
			<Pencil className="w-[11px] h-[11px]" aria-hidden="true" />
		</button>
	);

	const budgetBlock = budgetsFailed ? (
		<p className="mt-3 text-[12.5px] text-muted-foreground font-medium">
			Budgets aren't available right now.
		</p>
	) : budgets === undefined ? null : budgets.length === 0 ? (
		<p className="mt-2.5">
			<button type="button" onClick={editClientBudget} className={LINKISH}>
				Set a budget
			</button>
		</p>
	) : (
		<section aria-label={`${billing.name}'s budgets`} className="mt-3">
			<h3 className={LABEL}>Budget</h3>
			<ul className="mt-1 flex flex-col">
				{ownBudget && (
					<li className="py-2">
						<BillingBudgetRow
							status={ownBudget}
							now={now}
							title={billing.name}
							actions={pencil(billing.name, editClientBudget)}
						/>
					</li>
				)}
				{projectBudgets.map((status) => (
					<li key={status.scopeId} className="py-2 border-t border-border first:border-t-0">
						<BillingBudgetRow
							status={status}
							now={now}
							title={status.name}
							actions={pencil(status.name, () => editProjectBudget(status))}
							unpricedAction={
								<Link
									to={`/project/${status.scopeId}`}
									className="font-bold underline underline-offset-[3px] rounded focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
								>
									Set its rate
								</Link>
							}
						/>
					</li>
				))}
			</ul>
			{!ownBudget && (
				<button type="button" onClick={editClientBudget} className={LINKISH}>
					Set a budget for {billing.name}
				</button>
			)}
		</section>
	);

	const handleArchive = () => {
		const write = billing.archived ? unarchive : archive;
		write.mutate(billing.clientId, {
			onSuccess: () => toast.success(billing.archived ? "Client restored" : "Client archived"),
			onError: (err) => toast.error(describeError(err, "Failed to update the client")),
		});
	};

	const handleDelete = () =>
		remove.mutate(billing.clientId, {
			onSuccess: () => toast.success("Client deleted"),
			// CLIENT_HAS_PROJECTS says to archive instead, in the API's words.
			onError: (err) => toast.error(describeError(err, "Failed to delete the client")),
			onSettled: () => setConfirmingDelete(false),
		});

	return (
		<Panel role="region" aria-label={billing.name} padding="px-6 py-[22px]">
			<div className="flex items-start gap-x-3 gap-y-1 flex-wrap">
				<div className="min-w-0">
					<h2 className="font-heading text-xl font-extrabold tracking-[-0.01em] text-foreground flex items-center gap-2 flex-wrap">
						{billing.name}
						{billing.archived && (
							<span className="font-body text-[9.5px] font-bold tracking-[0.1em] uppercase px-[9px] py-0.5 rounded-full bg-tint-other text-tint-other-ink">
								Archived
							</span>
						)}
					</h2>
					<p className="text-[12.5px] text-muted-foreground font-medium mt-0.5">
						{[
							client ? rateToday(client, todayIso) : null,
							currency,
							client?.contactName ?? null,
							client?.contactEmail ?? null,
						]
							.filter((part): part is string => part !== null)
							.join(" · ")}
					</p>
				</div>
				<div className="ml-auto flex items-center gap-3">
					{confirmingDelete ? (
						<span className="inline-flex items-center gap-1.5 text-[12.5px] font-medium">
							Delete {billing.name}?
							<Button
								type="button"
								variant="destructive"
								size="sm"
								className="h-7 px-2.5 text-xs"
								disabled={pending}
								onClick={handleDelete}
							>
								Delete
							</Button>
							<Button
								type="button"
								variant="ghost"
								size="sm"
								className="h-7 px-2.5 text-xs"
								onClick={() => setConfirmingDelete(false)}
							>
								Cancel
							</Button>
						</span>
					) : (
						<>
							<button type="button" onClick={onEdit} disabled={!client} className={LINKISH}>
								Edit
							</button>
							<button type="button" onClick={handleArchive} disabled={pending} className={LINKISH}>
								{billing.archived ? "Restore" : "Archive"}
							</button>
							{/* Refused while a project is billed to it: archive is the way out. */}
							{billedProjects === 0 && (
								<button
									type="button"
									onClick={() => setConfirmingDelete(true)}
									disabled={pending}
									className={cn(LINKISH, "text-destructive-ink")}
								>
									Delete
								</button>
							)}
						</>
					)}
				</div>
			</div>

			{billing.lines.length === 0 && billing.entries.length === 0 ? (
				<>
					<p className="mt-3 text-[12.5px] text-muted-foreground font-medium">
						{/* A running timer is left out of the month until it stops. */}
						{billing.running
							? `Nothing finished for ${billing.name} in ${monthName} yet: a timer is running, and counts once stopped.`
							: `Nothing logged for ${billing.name} in ${monthName}.`}
					</p>
					{budgetBlock}
				</>
			) : (
				<>
					<p className="mt-3 font-mono text-[15px] font-bold text-foreground">
						{hoursText(billing.billableHours)}{" "}
						<span className="font-body font-medium text-muted-foreground">billable</span>
						{billing.lines.some((line) => line.amountMinor !== undefined) && (
							<> · {money(billing.amountMinor)}</>
						)}
						{billing.nonBillableHours > 0 && (
							<span className="font-body text-[12.5px] font-medium text-muted-foreground">
								{" "}
								· {hoursText(billing.nonBillableHours)} not billed
							</span>
						)}
					</p>

					{budgetBlock}

					{billing.lines.length > 0 && (
						<div className="mt-3 -mx-1 overflow-x-auto">
							<table className="w-full text-[12.5px] border-collapse">
								<caption className="sr-only">
									{billing.name} in {monthName}, by project and rate
								</caption>
								<thead>
									<tr className="text-left">
										<th scope="col" className={cn(TH, "px-1")}>
											Project
										</th>
										<th scope="col" className={cn(TH, "px-1")}>
											Rate
										</th>
										{/* Under the project's name on a phone: the run is what tells two lines apart. */}
										<th scope="col" className={cn(TH, "px-1 hidden sm:table-cell")}>
											Days
										</th>
										<th scope="col" className={cn(TH, "px-1 text-right")}>
											Hours
										</th>
										<th scope="col" className={cn(TH, "px-1 text-right")}>
											Amount
										</th>
									</tr>
								</thead>
								<tbody>
									{billing.lines.map((line) => (
										<tr
											key={`${line.projectId}-${line.first}`}
											className="border-t border-border align-baseline"
										>
											<td className="px-1 py-2 font-bold text-foreground">
												{line.projectName}
												<span className="sm:hidden block font-mono text-[11px] text-muted-foreground">
													{days(line.first, line.last)}
												</span>
											</td>
											<td className="px-1 py-2 whitespace-nowrap">
												{line.rateMinor !== undefined ? (
													<>
														<span className="font-mono font-bold text-foreground">
															{formatRate(line.rateMinor, currency, minorUnits)}
														</span>
														<span className="block text-[11px] text-muted-foreground font-medium">
															{line.source === "project" ? "own rate" : "client's rate"}
														</span>
													</>
												) : (
													<span className="font-bold text-destructive-ink">No rate</span>
												)}
											</td>
											<td className="px-1 py-2 whitespace-nowrap font-mono text-muted-foreground font-bold hidden sm:table-cell">
												{days(line.first, line.last)}
											</td>
											<td className="px-1 py-2 text-right font-mono font-bold text-foreground">
												{line.hours.toFixed(2)}
											</td>
											<td className="px-1 py-2 text-right font-mono font-bold text-foreground whitespace-nowrap">
												{line.amountMinor !== undefined ? money(line.amountMinor) : "—"}
											</td>
										</tr>
									))}
								</tbody>
							</table>
						</div>
					)}

					{[...unpriced].map(([projectId, { name, hours }]) => (
						<p
							key={projectId}
							className="mt-2.5 rounded-2xl bg-tint-sick px-3 py-2 text-[12.5px] font-medium text-tint-sick-ink"
						>
							{name} has {hoursText(hours)} with no rate, so no amount.{" "}
							<Link
								to={`/project/${projectId}`}
								className="font-bold underline underline-offset-[3px] rounded focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
							>
								Set its rate
							</Link>{" "}
							or give {billing.name} a default rate.
						</p>
					))}

					{billing.entries.length > 0 && (
						<div className="mt-3">
							<button
								type="button"
								aria-expanded={entriesOpen}
								onClick={() => setEntriesOpen((open) => !open)}
								className={cn(
									LABEL,
									"inline-flex items-center gap-1 rounded-full hover:text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
								)}
							>
								<ChevronRight
									className={cn("w-3 h-3 transition-transform", entriesOpen && "rotate-90")}
									aria-hidden="true"
								/>
								Entries ({billing.entries.length})
							</button>
							{entriesOpen && (
								<ul className="mt-1.5 flex flex-col">
									{billing.entries.map((entry) => (
										<EntryRow
											key={entry.beatId}
											entry={entry}
											projectName={nameOf(entry.projectId)}
											billing={projectBillings?.get(entry.projectId)}
											overrides={overrides}
											tz={tz}
										/>
									))}
								</ul>
							)}
						</div>
					)}
				</>
			)}

			{budgetEditor && (
				<BillingBudgetDialog
					scope={budgetEditor.scope}
					scopeId={budgetEditor.scopeId}
					name={budgetEditor.name}
					currency={currency}
					minorUnits={minorUnits}
					budget={budgetEditor.status}
					billingStartedOn={budgetEditor.billingStartedOn}
					todayIso={todayIso}
					onClose={() => setBudgetEditor(null)}
				/>
			)}
		</Panel>
	);
}
