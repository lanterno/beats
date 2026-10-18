/**
 * Clients Page — `/clients`: what is billable in a month, per client
 * (docs/billing.md). The sentence first (`summary.ts`), then one panel per
 * client with its lines and entries (`ClientPanel`), then the freelance
 * hours no client is billed for. The month is the URL's `?month=`, stepped
 * with ‹ ›, and the current month is month to date.
 *
 * The month's figures are the API's (`/api/billing/month`, in the browser's
 * zone), never added up here; the page only names them. In the current
 * month each client's billing budgets (`/api/billing/budgets`, as of
 * today) follow its figure, and the sentence notes each one near or used
 * up; a past month shows none, since a budget is never read against a
 * month already over. A client's record
 * is edited in `ClientDialog`, and a change to a month already over asks
 * first, in the API's words (`withPastConsent`). When the billing routes
 * cannot be reached — an older API during a deploy — the page says so and
 * nothing else on the site is affected.
 */

import { Briefcase, ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import {
	monthOf,
	nextMonth,
	prevMonth,
	useBillableOverrides,
	useBillingBudgets,
	useBillingMonth,
	useProjectBillings,
	withPastConsent,
} from "@/entities/billing";
import type { Client, ClientInput } from "@/entities/client";
import {
	ClientDialog,
	useClients,
	useCreateClient,
	useUnarchiveClient,
	useUpdateClient,
} from "@/entities/client";
import { useArchivedProjects, useProjects } from "@/entities/project";
import { describeError } from "@/shared/api";
import { browserTimeZone, cn, hoursText, todayIso as readToday, useNow } from "@/shared/lib";
import { Button, Panel, useConfirm } from "@/shared/ui";
import { ClientPanel } from "./ClientPanel";
import { describeMonth, monthName } from "./summary";
import { useOpenMonth } from "./useOpenMonth";

type Editor = { mode: "new" } | { mode: "edit"; client: Client };

const LINKISH =
	"text-accent-ink text-[12.5px] font-bold hover:underline underline-offset-[3px] rounded-full disabled:opacity-40 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";
/** The ‹ › on the sky: the card is their ground, since a wash would vanish there. */
const SKY_NAV =
	"grid place-items-center w-8 h-8 rounded-full text-foreground hover:bg-secondary transition-colors disabled:opacity-40 disabled:pointer-events-none focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** "October 2026". */
function monthTitle(month: string): string {
	const date = new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1, 1, 12);
	return date.toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

export default function Clients() {
	const today = readToday();
	const tz = browserTimeZone();
	const [month, setMonth] = useOpenMonth(today);
	const current = month === monthOf(today);
	const [editor, setEditor] = useState<Editor | null>(null);
	const [archivedOpen, setArchivedOpen] = useState(false);
	const { confirm, confirmDialog } = useConfirm();

	const monthQuery = useBillingMonth(month, tz);
	const budgetsQuery = useBillingBudgets(tz, { enabled: current });
	// A failed refetch keeps the last good data beside its error: read none,
	// so no note or row outlives the failure line.
	const budgetsFailed = current && budgetsQuery.isError;
	const budgets = current && !budgetsFailed ? budgetsQuery.data : undefined;
	// A minute's tick, only while a running timer could cross a threshold on screen.
	const now = useNow(60_000, { enabled: (budgets ?? []).some((b) => b.running) });
	const { data: clients, isLoading: clientsLoading } = useClients();
	const { data: archivedClients } = useClients({ archived: true });
	const { data: billings } = useProjectBillings();
	const { data: overrides } = useBillableOverrides();
	const { data: projects } = useProjects();
	const { data: archivedProjects } = useArchivedProjects();
	const create = useCreateClient();
	const update = useUpdateClient();
	const unarchive = useUnarchiveClient();

	const records = new Map(
		[...(clients ?? []), ...(archivedClients ?? [])].map((client) => [client.id, client]),
	);
	const projectNames = new Map(
		[...(projects ?? []), ...(archivedProjects ?? [])].map((p) => [p.id, p.name]),
	);
	const report = monthQuery.data;
	const summary = report ? describeMonth(report, { current, budgets, now }) : null;
	const noClients =
		!clientsLoading &&
		(clients ?? []).length === 0 &&
		(archivedClients ?? []).length === 0 &&
		(report?.clients.length ?? 0) === 0;
	const name = monthName(month);
	// The freelance hours billed to no one, with or without a client yet:
	// with none, a first freelance project's hours are all there is.
	const unattached = report && report.unattached.length > 0 && (
		<Panel role="region" aria-label="Not billed to a client" padding="px-6 py-[22px]">
			<p className="text-[13px] font-medium text-foreground leading-normal">
				<span className="font-bold">Not billed to a client:</span>{" "}
				{report.unattached.map((item, i) => (
					<span key={item.projectId}>
						{i > 0 && " · "}
						{item.name} ({hoursText(item.hours)}){" "}
						<Link to={`/project/${item.projectId}`} className={LINKISH}>
							Bill it
						</Link>
					</span>
				))}
			</p>
			<p className="mt-1 text-xs text-muted-foreground font-medium">
				Freelance hours in {name} that no client's figure counts.
			</p>
		</Panel>
	);

	const save = async (input: ClientInput): Promise<boolean> => {
		if (editor?.mode !== "edit") {
			await create.mutateAsync(input);
			toast.success("Client added");
			return true;
		}
		const clientId = editor.client.id;
		const saved = await withPastConsent(
			(rewritePast) => update.mutateAsync({ clientId, input, rewritePast }),
			(detail) =>
				confirm({
					title: "Change a month already over?",
					detail,
					confirmLabel: "Change it",
					cancelLabel: "Keep it",
				}),
		);
		if (saved === undefined) return false;
		toast.success("Client saved");
		return true;
	};

	return (
		<div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 space-y-5 pb-24">
			<header className="flex items-center gap-3 flex-wrap">
				<Briefcase className="w-5 h-5 text-muted-foreground" aria-hidden="true" />
				<h1 className="font-heading text-2xl font-extrabold tracking-[-0.02em] text-foreground">
					Clients
				</h1>
				<Button
					type="button"
					size="sm"
					className="ml-auto"
					onClick={() => setEditor({ mode: "new" })}
				>
					<Plus className="w-3.5 h-3.5" aria-hidden="true" />
					New client
				</Button>
			</header>

			<div className="flex items-center gap-3 flex-wrap">
				<div className="inline-flex items-center gap-1 rounded-full bg-sidebar shadow-soft p-1">
					<button
						type="button"
						onClick={() => setMonth(prevMonth(month))}
						aria-label="Previous month"
						className={SKY_NAV}
					>
						<ChevronLeft className="w-4 h-4" aria-hidden="true" />
					</button>
					<h2
						className="px-2 font-heading text-[15px] font-extrabold text-foreground whitespace-nowrap"
						aria-live="polite"
					>
						{monthTitle(month)}
						{current && (
							<span className="font-body font-medium text-muted-foreground"> · so far</span>
						)}
					</h2>
					<button
						type="button"
						onClick={() => setMonth(nextMonth(month))}
						disabled={current}
						aria-label="Next month"
						className={SKY_NAV}
					>
						<ChevronRight className="w-4 h-4" aria-hidden="true" />
					</button>
				</div>
				{!current && (
					<button
						type="button"
						onClick={() => setMonth(monthOf(today))}
						className={cn(LINKISH, "rounded-full bg-sidebar shadow-soft px-3 py-1.5")}
					>
						This month
					</button>
				)}
			</div>

			{monthQuery.error ? (
				<Panel role="alert" padding="px-6 py-[22px]">
					<p className="font-heading text-lg font-extrabold text-foreground">
						Billing isn't available right now.
					</p>
					<p className="mt-1 text-[12.5px] text-muted-foreground font-medium">
						The rest of the site works as usual.
					</p>
					{/* The API's words as they came, on a line of their own: they are
					    not a sentence of this page's, and may not end in a full stop. */}
					<p className="mt-1 text-xs text-muted-foreground font-medium">
						{describeError(monthQuery.error, "The figures could not be read.")}
					</p>
				</Panel>
			) : !report ? (
				<p className="text-sm text-muted-foreground px-2">Loading…</p>
			) : noClients ? (
				<>
					<Panel padding="px-6 py-[22px]">
						<p className="font-heading text-lg font-extrabold text-foreground">
							Clients are who you bill.
						</p>
						<p className="mt-1 text-[13px] text-muted-foreground font-medium leading-normal">
							Add one, then choose it on a freelance project.
						</p>
						<Button
							type="button"
							variant="secondary"
							size="sm"
							className="mt-3"
							onClick={() => setEditor({ mode: "new" })}
						>
							<Plus aria-hidden="true" />
							Add a client
						</Button>
					</Panel>
					{unattached}
				</>
			) : (
				<>
					{summary && (
						<Panel role="region" aria-label="Summary" padding="px-6 py-[22px]">
							<p className="font-heading text-xl font-extrabold tracking-[-0.01em] text-foreground leading-snug">
								{summary.headline}
							</p>
							{summary.notes.length > 0 && (
								<p className="mt-1.5 text-[13px] text-muted-foreground font-medium leading-normal">
									{summary.notes.join(" ")}
								</p>
							)}
						</Panel>
					)}

					{report.clients.map((billing) => {
						const client = records.get(billing.clientId);
						return (
							<ClientPanel
								key={billing.clientId}
								billing={billing}
								client={client}
								todayIso={today}
								tz={tz}
								monthName={name}
								projectNames={projectNames}
								projectBillings={billings}
								overrides={overrides}
								budgets={budgets?.filter((b) => b.clientId === billing.clientId)}
								budgetsFailed={budgetsFailed}
								now={now}
								onEdit={() => client && setEditor({ mode: "edit", client })}
							/>
						);
					})}

					{unattached}

					{(archivedClients ?? []).length > 0 && (
						<div className="px-2">
							<button
								type="button"
								aria-expanded={archivedOpen}
								onClick={() => setArchivedOpen((open) => !open)}
								className={LINKISH}
							>
								{archivedOpen
									? "Hide archived clients"
									: `Archived clients (${(archivedClients ?? []).length})`}
							</button>
							{archivedOpen && (
								<Panel padding="px-6 py-3" className="mt-2">
									<ul className="divide-y divide-border">
										{(archivedClients ?? []).map((client) => (
											<li key={client.id} className="flex items-center gap-2 py-2 text-[12.5px]">
												<span className="font-bold text-foreground">{client.name}</span>
												<span className="text-muted-foreground">{client.currency}</span>
												<button
													type="button"
													onClick={() =>
														unarchive.mutate(client.id, {
															onSuccess: () => toast.success("Client restored"),
															onError: (err) =>
																toast.error(describeError(err, "Failed to restore the client")),
														})
													}
													disabled={unarchive.isPending}
													className={cn(LINKISH, "ml-auto")}
												>
													Restore
												</button>
											</li>
										))}
									</ul>
								</Panel>
							)}
						</div>
					)}
				</>
			)}

			{editor && (
				<ClientDialog
					key={editor.mode === "edit" ? editor.client.id : "new"}
					client={editor.mode === "edit" ? editor.client : undefined}
					todayIso={today}
					onSave={save}
					onClose={() => setEditor(null)}
				/>
			)}
			{confirmDialog}
		</div>
	);
}
