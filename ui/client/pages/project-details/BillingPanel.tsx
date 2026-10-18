/**
 * BillingPanel — the rail's Billing on a freelance project
 * (docs/project-page.md, docs/billing.md): who the work is for, and its
 * terms as a register — "Since Mar 1, 2026: billable at the client's rate,
 * €85.00/h", "From Nov 1, 2026: not billable" — with edit and remove, a
 * change from a day, and this month's billable figure from the API, which
 * links to the Clients page. Without billing it asks who the work is for.
 *
 * Under the month's figure sits the project's billing budget (docs/billing.md,
 * phase 1b) — its row with edit and remove, or "+ Set a budget" — and, when
 * its client has a budget of its own, a read-only line saying this project
 * counts toward it too. With a budget, "Stop billing" names it, and only
 * that confirmation sends `remove_billing_budget`; when the budgets cannot
 * be read the line says so and the rest of the panel is as it was.
 *
 * Every change PUTs the whole billing through `BillingDialog`; a remove
 * here and "Stop billing" go through `withPastConsent` as the dialog's
 * saves do, so nothing in a month already over changes unasked. The page
 * reads the billing (it is the session rows' too) and hands it in; when it
 * cannot be read — an older API during a deploy — the panel says so and
 * the rest of the page works.
 */

import { Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import type { BillingBudgetStatus, BillingTerm, ProjectBilling } from "@/entities/billing";
import {
	BillingBudgetDialog,
	BillingBudgetRow,
	inForceOn,
	monthOf,
	useBillingBudgets,
	useBillingMonth,
	useRemoveBillingBudget,
	useRemoveProjectBilling,
	useSetProjectBilling,
	withPastConsent,
} from "@/entities/billing";
import type { Client } from "@/entities/client";
import { useClients } from "@/entities/client";
import type { ProjectWithDuration } from "@/entities/project";
import { describeError } from "@/shared/api";
import {
	browserTimeZone,
	cn,
	formatDateShort,
	formatMoney,
	formatRate,
	hoursText,
	parseIsoDate,
	useNow,
} from "@/shared/lib";
import { Button, Panel, useConfirm } from "@/shared/ui";
import { BillingDialog, type BillingDialogMode } from "./BillingDialog";
import { plainDate } from "./dates";
import { LABEL, LINKISH, SUB } from "./styles";

export interface BillingPanelProps {
	project: ProjectWithDuration;
	todayIso: string;
	/** The local day of the project's first session — where "Bill this project" starts. */
	firstTrackedIso?: string;
	/** The project's billing; undefined while it is not billed. */
	billing?: ProjectBilling;
	loading: boolean;
	error: unknown;
}

const STATUS =
	"font-body text-[9.5px] font-bold tracking-[0.1em] uppercase px-[9px] py-0.5 rounded-full whitespace-nowrap";
const OP =
	"grid place-items-center w-[22px] h-[22px] rounded-full text-muted-foreground hover:bg-sidebar-accent hover:text-foreground transition-colors disabled:opacity-40 disabled:pointer-events-none focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";
/** Edit and remove: hidden until the row is hovered or focused, where there is hover at all. */
const OPS =
	"inline-flex gap-0.5 [@media(hover:hover)]:opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity";
const ROW =
	"group grid grid-cols-[minmax(0,1fr)_auto] [grid-template-areas:'from_st'_'what_what'] gap-x-2 gap-y-0.5 items-center py-[9px] border-t border-border text-[12.5px]";

function sortTerms(terms: BillingTerm[]): BillingTerm[] {
	return [...terms].sort((a, b) => a.effectiveFrom.localeCompare(b.effectiveFrom));
}

/**
 * "billable at the client's rate, €85.00/h", "billable at €95.00/h", "not
 * billable" — the client's rate as it stands on the term's first day, or
 * today's while the term is in force.
 */
function describeBillingTerm(
	term: BillingTerm,
	billing: ProjectBilling,
	client: Client | undefined,
	day: string,
): string {
	if (!term.billable) return "not billable";
	if (term.rateMinor !== undefined) {
		return `billable at ${formatRate(term.rateMinor, billing.currency, billing.minorUnits)}`;
	}
	const rate = client ? inForceOn(client.rates, day) : undefined;
	return rate
		? `billable at the client's rate, ${formatRate(rate.rateMinor, billing.currency, billing.minorUnits)}`
		: "billable at the client's rate, which has none yet";
}

/**
 * "4.5 h left this month", "€120.00 over since Sep 1", "starts Nov 1": what
 * is left of the client's budget, in the API's figures, for the line that
 * says the project counts toward it.
 */
function clientBudgetLeft(status: BillingBudgetStatus): string {
	const day = (iso: string) => {
		const d = parseIsoDate(iso);
		return d ? formatDateShort(d) : iso;
	};
	if (status.upcoming) return `starts ${day(status.first)}`;
	const hours = status.unit === "hours";
	const remaining = (hours ? status.remainingHours : status.remainingMinor) ?? 0;
	const figure = hours
		? hoursText(Math.abs(remaining))
		: formatMoney(Math.abs(remaining), status.currency, status.minorUnits);
	const when = status.period === "monthly" ? "this month" : `since ${day(status.first)}`;
	if (remaining < 0) return `${figure} over ${when}`;
	if (remaining === 0) return `used up ${when}`;
	return `${figure} left ${when}`;
}

function Billed({
	project,
	billing,
	todayIso,
	firstTrackedIso,
}: {
	project: ProjectWithDuration;
	billing: ProjectBilling;
	todayIso: string;
	firstTrackedIso?: string;
}) {
	const tz = browserTimeZone();
	const { data: active } = useClients();
	const { data: archived } = useClients({ archived: true });
	const month = useBillingMonth(monthOf(todayIso), tz);
	const setBilling = useSetProjectBilling();
	const removeBilling = useRemoveProjectBilling();
	const budgets = useBillingBudgets(tz);
	const removeBudget = useRemoveBillingBudget();
	const { confirm, confirmDialog } = useConfirm();
	const [dialog, setDialog] = useState<{ key: number; mode: BillingDialogMode } | null>(null);
	const [pendingIndex, setPendingIndex] = useState<number | null>(null);
	const [confirmingStop, setConfirmingStop] = useState(false);
	const [budgetOpen, setBudgetOpen] = useState(false);
	const dialogs = useRef(0);
	const changeButton = useRef<HTMLButtonElement>(null);
	const budgetButton = useRef<HTMLButtonElement>(null);

	const client = [...(active ?? []), ...(archived ?? [])].find((c) => c.id === billing.clientId);
	const terms = sortTerms(billing.terms);
	const inForce = inForceOn(terms, todayIso);
	// A failed refetch keeps the last good data beside its error: read none,
	// so the client's line and the confirmation do not outlive the failure.
	const budgetsRead = budgets.isError ? undefined : budgets.data;
	const budget = budgetsRead?.find((b) => b.scope === "project" && b.scopeId === project.id);
	const clientBudget = budgetsRead?.find(
		(b) => b.scope === "client" && b.scopeId === billing.clientId,
	);
	// A minute's tick, only while a running timer could cross a threshold here.
	const now = useNow(60_000, { enabled: Boolean(budget?.running || clientBudget?.running) });
	const busy = setBilling.isPending || removeBilling.isPending || removeBudget.isPending;
	const askPast = (detail: string) =>
		confirm({
			title: "Change a month already over?",
			detail,
			confirmLabel: "Change it",
			cancelLabel: "Keep it",
		});

	const open = (mode: BillingDialogMode) => {
		dialogs.current += 1;
		setDialog({ key: dialogs.current, mode });
	};

	const handleRemove = async (index: number) => {
		setPendingIndex(index);
		try {
			const saved = await withPastConsent(
				(rewritePast) =>
					setBilling.mutateAsync({
						projectId: project.id,
						input: { clientId: billing.clientId, terms: terms.filter((_, i) => i !== index) },
						rewritePast,
					}),
				askPast,
			);
			if (saved !== undefined) toast.success("Change removed");
		} catch (err) {
			toast.error(describeError(err, "Failed to remove the change"));
		} finally {
			setPendingIndex(null);
		}
	};

	/**
	 * `removeBillingBudget` is true only from the confirmation that named the
	 * budget: a tab that never saw one sends false, and the API's refusal
	 * shows in its own words.
	 */
	const handleStop = async (removeBillingBudget: boolean) => {
		try {
			const stopped = await withPastConsent(async (rewritePast) => {
				await removeBilling.mutateAsync({
					projectId: project.id,
					rewritePast,
					removeBillingBudget,
				});
				return true;
			}, askPast);
			if (stopped) toast.success(`${project.name} is no longer billed`);
		} catch (err) {
			toast.error(describeError(err, "Failed to stop billing"));
		} finally {
			setConfirmingStop(false);
		}
	};

	const handleRemoveBudget = () =>
		removeBudget.mutate(
			{ scope: "project", scopeId: project.id },
			{
				onSuccess: () => toast.success("Budget removed"),
				onError: (err) => toast.error(describeError(err, "Failed to remove the budget")),
			},
		);

	// This month's figures for the project: its lines' sums, as the Clients page shows them.
	const lines = (month.data?.clients ?? [])
		.flatMap((c) => c.lines)
		.filter((line) => line.projectId === project.id);
	const hours = Math.round(lines.reduce((sum, line) => sum + line.hours, 0) * 100) / 100;
	const priced = lines.filter((line) => line.amountMinor !== undefined);
	const amount = priced.reduce((sum, line) => sum + (line.amountMinor ?? 0), 0);

	return (
		<>
			<div className="flex items-baseline gap-x-3 gap-y-2 flex-wrap">
				<h3 className={LABEL}>
					Billing <span className={SUB}>{client?.name ?? "…"}</span>
				</h3>
				<button
					type="button"
					onClick={() => open({ kind: "client" })}
					disabled={busy}
					className={cn(LINKISH, "ml-auto")}
				>
					Change client
				</button>
			</div>

			{terms.length === 0 ? (
				<p className="mt-2.5 text-[12.5px] text-muted-foreground font-medium">
					No terms: none of its time is billable.
				</p>
			) : (
				<ul className="mt-2.5 flex flex-col" aria-label="Billing terms">
					{terms.map((term, index) => {
						const when = plainDate(term.effectiveFrom);
						const planned = term.effectiveFrom > todayIso;
						const current = term === inForce;
						return (
							<li key={term.effectiveFrom} className={ROW}>
								<span className="[grid-area:from] text-[11.5px] text-muted-foreground whitespace-nowrap font-bold font-mono">
									{planned ? "From" : "Since"} {when}
								</span>
								<span className="[grid-area:st] inline-flex gap-1.5 items-center justify-self-end">
									{current && (
										<span className={cn(STATUS, "bg-tint-holiday text-tint-holiday-ink")}>
											In force
										</span>
									)}
									{planned && (
										<span className={cn(STATUS, "bg-tint-other text-tint-other-ink")}>Planned</span>
									)}
									<span className={OPS}>
										<button
											type="button"
											onClick={() => open({ kind: "term", index })}
											disabled={busy}
											aria-label={`Edit the change from ${when}`}
											className={OP}
										>
											<Pencil className="w-[11px] h-[11px]" aria-hidden="true" />
										</button>
										<button
											type="button"
											onClick={() => void handleRemove(index)}
											disabled={busy || terms.length <= 1}
											aria-label={`Remove the change from ${when}`}
											title={terms.length <= 1 ? "Stop billing to remove the last one" : undefined}
											className={cn(OP, "hover:text-destructive")}
										>
											{pendingIndex === index ? (
												<Loader2 className="w-[11px] h-[11px] animate-spin" aria-hidden="true" />
											) : (
												<Trash2 className="w-[11px] h-[11px]" aria-hidden="true" />
											)}
										</button>
									</span>
								</span>
								<span className="[grid-area:what] min-w-0 text-foreground font-medium">
									{describeBillingTerm(
										term,
										billing,
										client,
										current ? todayIso : term.effectiveFrom,
									)}
								</span>
							</li>
						);
					})}
				</ul>
			)}

			<div className="mt-3.5">
				<Button
					ref={changeButton}
					type="button"
					variant="secondary"
					size="sm"
					onClick={() => open({ kind: "term" })}
					disabled={busy}
				>
					<Plus aria-hidden="true" />
					Change from…
				</Button>
			</div>

			{month.data && (
				<p className="mt-3 text-[12.5px] font-medium text-muted-foreground">
					This month:{" "}
					<span className="font-mono font-bold text-foreground">
						{hours} h billable
						{priced.length > 0 && ` · ${formatMoney(amount, billing.currency, billing.minorUnits)}`}
					</span>{" "}
					<Link to="/clients" className={LINKISH}>
						→ Clients
					</Link>
				</p>
			)}

			<div className="mt-3">
				{budgets.isError ? (
					<p className="text-[12.5px] text-muted-foreground font-medium">
						Budgets aren't available right now.
					</p>
				) : budget ? (
					<BillingBudgetRow
						status={budget}
						now={now}
						title="Budget"
						actions={
							<span className={OPS}>
								<button
									ref={budgetButton}
									type="button"
									onClick={() => setBudgetOpen(true)}
									disabled={busy}
									aria-label="Edit the budget"
									className={OP}
								>
									<Pencil className="w-[11px] h-[11px]" aria-hidden="true" />
								</button>
								<button
									type="button"
									onClick={handleRemoveBudget}
									disabled={busy}
									aria-label="Remove the budget"
									className={cn(OP, "hover:text-destructive")}
								>
									{removeBudget.isPending ? (
										<Loader2 className="w-[11px] h-[11px] animate-spin" aria-hidden="true" />
									) : (
										<Trash2 className="w-[11px] h-[11px]" aria-hidden="true" />
									)}
								</button>
							</span>
						}
						className="group"
					/>
				) : budgets.data ? (
					<button
						ref={budgetButton}
						type="button"
						onClick={() => setBudgetOpen(true)}
						disabled={busy}
						className={LINKISH}
					>
						+ Set a budget
					</button>
				) : null}
				{clientBudget && (
					<p className="mt-1.5 text-[12.5px] font-medium text-muted-foreground">
						Also counts toward {clientBudget.name}'s budget:{" "}
						<span className="font-mono font-bold text-foreground">
							{clientBudgetLeft(clientBudget)}
						</span>{" "}
						<Link to="/clients" className={LINKISH}>
							→ Clients
						</Link>
					</p>
				)}
			</div>

			<div className="mt-2.5 pt-2.5 border-t border-border text-xs text-muted-foreground font-medium">
				{confirmingStop ? (
					<span className="inline-flex flex-wrap items-center gap-1.5">
						{budget
							? `Stop billing ${project.name}? Its terms and its budget go; its hours stay.`
							: `Stop billing ${project.name}? Its terms go; its hours stay.`}
						<Button
							type="button"
							variant="destructive"
							size="sm"
							className="h-7 px-2.5 text-xs"
							disabled={busy}
							onClick={() => void handleStop(budget !== undefined)}
						>
							Stop billing
						</Button>
						<Button
							type="button"
							variant="ghost"
							size="sm"
							className="h-7 px-2.5 text-xs"
							onClick={() => setConfirmingStop(false)}
						>
							Cancel
						</Button>
					</span>
				) : (
					<button
						type="button"
						onClick={() => setConfirmingStop(true)}
						disabled={busy}
						className={cn(LINKISH, "text-destructive-ink text-xs")}
					>
						Stop billing
					</button>
				)}
			</div>

			{dialog && (
				<BillingDialog
					key={dialog.key}
					project={project}
					mode={dialog.mode}
					billing={billing}
					todayIso={todayIso}
					firstTrackedIso={firstTrackedIso}
					returnFocus={() => changeButton.current}
					onClose={() => setDialog((d) => (d?.key === dialog.key ? null : d))}
				/>
			)}
			{budgetOpen && (
				<BillingBudgetDialog
					scope="project"
					scopeId={project.id}
					name={project.name}
					currency={billing.currency}
					minorUnits={billing.minorUnits}
					budget={budget}
					billingStartedOn={terms[0]?.effectiveFrom}
					todayIso={todayIso}
					returnFocus={() => budgetButton.current}
					onClose={() => setBudgetOpen(false)}
				/>
			)}
			{confirmDialog}
		</>
	);
}

export function BillingPanel({
	project,
	todayIso,
	firstTrackedIso,
	billing,
	loading,
	error,
}: BillingPanelProps) {
	const [attaching, setAttaching] = useState(false);
	const attachButton = useRef<HTMLButtonElement>(null);

	return (
		<Panel role="region" aria-label="Billing" padding="px-6 py-[22px]">
			{error ? (
				<>
					<h3 className={LABEL}>Billing</h3>
					<p role="alert" className="mt-2.5 text-[12.5px] text-muted-foreground font-medium">
						Billing isn't available right now.
					</p>
				</>
			) : loading ? (
				<>
					<h3 className={LABEL}>Billing</h3>
					<p className="mt-2.5 text-[12.5px] text-muted-foreground">Loading…</p>
				</>
			) : billing ? (
				<Billed
					project={project}
					billing={billing}
					todayIso={todayIso}
					firstTrackedIso={firstTrackedIso}
				/>
			) : (
				<>
					<h3 className={LABEL}>Billing</h3>
					<p className="mt-2.5 font-heading text-[15px] font-extrabold text-foreground">
						Who is this work for?
					</p>
					<p className="mt-0.5 text-[12.5px] text-muted-foreground font-medium leading-normal">
						Bill it to a client and its hours count in the month's figures on Clients.
					</p>
					<Button
						ref={attachButton}
						type="button"
						variant="secondary"
						size="sm"
						className="mt-3"
						onClick={() => setAttaching(true)}
					>
						Bill this project
					</Button>
					{attaching && (
						<BillingDialog
							project={project}
							mode={{ kind: "attach" }}
							todayIso={todayIso}
							firstTrackedIso={firstTrackedIso}
							returnFocus={() => attachButton.current}
							onClose={() => setAttaching(false)}
						/>
					)}
				</>
			)}
		</Panel>
	);
}
