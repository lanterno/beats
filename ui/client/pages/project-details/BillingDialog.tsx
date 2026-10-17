/**
 * BillingDialog — a freelance project's billing, one question at a time
 * (docs/billing.md, docs/project-page.md):
 *
 * - **Bill this project**: who the work is for, billable from when, and at
 *   whose rate. "Billable from" starts on the project's first tracked day
 *   ("All of its time so far"), or today when nothing is tracked yet; the
 *   user sees it and can move it, and that is the consent for history.
 * - **Change client**: the client alone. The link is not dated, so moving
 *   it moves every hour; a move that reaches a month already over asks.
 * - **A term**, added from a day or edited: billable or not from that day,
 *   at the client's rate or one of the project's own. The day is picked
 *   with a chip or the calendar, never filled in.
 *
 * Every save PUTs the whole billing — the client and every term — through
 * `withPastConsent`, which asks in the API's words before a change to a
 * month already over and sends again only if the user agrees. A refusal
 * lands on its input: a 422 on `terms.N.rate_minor` on the rate, a client
 * that is gone or in another currency on the client.
 */

import { useId, useState } from "react";
import { toast } from "sonner";
import type { BillingTerm, ProjectBilling } from "@/entities/billing";
import { inForceOn, useSetProjectBilling, withPastConsent } from "@/entities/billing";
import type { Client, ClientInput } from "@/entities/client";
import { ClientDialog, useClients, useCreateClient } from "@/entities/client";
import type { ProjectWithDuration } from "@/entities/project";
import { ApiError, apiFieldErrors, describeError } from "@/shared/api";
import { addIsoDays, cn, formatRate, minorToInput, parseIsoDate, parseMoney } from "@/shared/lib";
import { Button, Dialog, useConfirm } from "@/shared/ui";
import { longDate } from "./dates";
import { LABEL } from "./styles";

export type BillingDialogMode =
	| { kind: "attach" }
	| { kind: "client" }
	/** A term: the one at `index` of the billing's terms, or a new one. */
	| { kind: "term"; index?: number };

export interface BillingDialogProps {
	project: Pick<ProjectWithDuration, "id" | "name">;
	mode: BillingDialogMode;
	/** The project's billing; absent while it is not billed. */
	billing?: ProjectBilling;
	todayIso: string;
	/** The local day of the project's first session. */
	firstTrackedIso?: string;
	onClose: () => void;
	/** Where focus goes on close when the control that opened the dialog has gone. */
	returnFocus?: () => HTMLElement | null | undefined;
}

interface Errors {
	client?: string;
	from?: string;
	rate?: string;
	general: string[];
}

const NEW_CLIENT = "__new__";
const FIELD =
	"w-full min-w-0 bg-secondary border-0 rounded-xl text-foreground px-3 py-2 text-[13.5px] font-medium focus:outline-hidden focus:ring-[3px] focus:ring-accent aria-invalid:ring-2 aria-invalid:ring-destructive/60 disabled:opacity-60";
const ERROR = "mt-1 text-xs text-destructive-ink";
const CHIP =
	"inline-flex items-center rounded-full bg-secondary px-2.5 py-0.5 text-[11.5px] font-bold text-foreground hover:bg-sidebar-accent transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";
const SEGMENT =
	"px-[13px] py-[5px] rounded-full text-[12.5px] font-bold transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** The codes whose refusal is about the client chosen. */
const CLIENT_CODES = new Set(["CLIENT_NOT_FOUND", "CURRENCY_MISMATCH"]);

function sortTerms(terms: BillingTerm[]): BillingTerm[] {
	return [...terms].sort((a, b) => a.effectiveFrom.localeCompare(b.effectiveFrom));
}

/**
 * A refused save, onto the inputs. `edited` is where the term this dialog
 * wrote sits in the terms sent, so `terms.<edited>.rate_minor` is its rate;
 * a path about another term has no input here and reads as a message.
 */
function billingErrors(err: unknown, edited: number | undefined): Errors {
	const out: Errors = { general: [] };
	const fields = apiFieldErrors(err);
	if (Object.keys(fields).length === 0) {
		if (err instanceof ApiError && err.code && CLIENT_CODES.has(err.code)) out.client = err.message;
		else out.general.push(describeError(err, "Failed to save the billing"));
		return out;
	}
	for (const [path, message] of Object.entries(fields)) {
		const [head, index, leaf] = path.split(".");
		if (head === "client_id" && !out.client) out.client = message;
		else if (head === "terms" && edited !== undefined && Number(index) === edited) {
			if (leaf === "rate_minor" && !out.rate) out.rate = message;
			else if (leaf === "effective_from" && !out.from) out.from = message;
			else out.general.push(message);
		} else out.general.push(path ? `${path}: ${message}` : message);
	}
	return out;
}

function firstOfMonth(iso: string): string {
	return `${iso.slice(0, 7)}-01`;
}

function firstOfNextMonth(iso: string): string {
	return `${addIsoDays(firstOfMonth(iso), 32).slice(0, 7)}-01`;
}

export function BillingDialog({
	project,
	mode,
	billing,
	todayIso,
	firstTrackedIso,
	onClose,
	returnFocus,
}: BillingDialogProps) {
	const id = useId();
	const { data: activeClients } = useClients();
	const { data: archivedClients } = useClients({ archived: true });
	const setBilling = useSetProjectBilling();
	const createClient = useCreateClient();
	const { confirm, confirmDialog } = useConfirm();

	const terms = sortTerms(billing?.terms ?? []);
	const editing = mode.kind === "term" && mode.index !== undefined ? terms[mode.index] : undefined;
	// A new term starts from the rule in force today, on a day still to pick.
	const template = editing ?? inForceOn(terms, todayIso) ?? terms[terms.length - 1];
	const [clientId, setClientId] = useState(billing?.clientId ?? "");
	const [from, setFrom] = useState(
		mode.kind === "attach" ? (firstTrackedIso ?? todayIso) : (editing?.effectiveFrom ?? ""),
	);
	const [billable, setBillable] = useState(template?.billable ?? true);
	const [ownRate, setOwnRate] = useState(template?.rateMinor !== undefined);
	const [amount, setAmount] = useState(
		template?.rateMinor !== undefined && billing
			? minorToInput(template.rateMinor, billing.minorUnits)
			: "",
	);
	const [errors, setErrors] = useState<Errors>({ general: [] });
	const [busy, setBusy] = useState(false);
	const [addingClient, setAddingClient] = useState(false);

	const clients = activeClients ?? [];
	const all = new Map<string, Client>(
		[...clients, ...(archivedClients ?? [])].map((client) => [client.id, client]),
	);
	const client = all.get(clientId);
	const minorUnits = client?.minorUnits ?? billing?.minorUnits ?? 2;
	// The client's rate on the term's first day, or today's once that day has passed.
	const rateDay = from && from > todayIso ? from : todayIso;
	const clientRate = client ? inForceOn(client.rates, rateDay) : undefined;
	const asksClient = mode.kind === "attach" || mode.kind === "client";
	const asksFrom = mode.kind === "attach" || mode.kind === "term";
	const asksRate = asksFrom && billable;
	const chips: [string, string][] = [
		["1st of this month", firstOfMonth(todayIso)],
		["Today", todayIso],
		["1st of next month", firstOfNextMonth(todayIso)],
	];
	const fromHint =
		mode.kind === "attach" && from === firstTrackedIso
			? "All of its time so far"
			: from === todayIso
				? "From today"
				: null;

	const save = async () => {
		const next: Errors = { general: [] };
		if (asksClient && !client) next.client = "Choose who the work is for.";
		let term: BillingTerm | undefined;
		if (asksFrom) {
			if (!parseIsoDate(from)) next.from = "Pick the day it starts.";
			else if (terms.some((t) => t !== editing && t.effectiveFrom === from)) {
				next.from = "Another change starts on this day.";
			}
			let rateMinor: number | undefined;
			if (asksRate && ownRate) {
				const parsed = parseMoney(amount, minorUnits);
				if (parsed.ok) rateMinor = parsed.minor;
				else next.rate = parsed.reason;
			}
			term = { effectiveFrom: from, billable, rateMinor };
		}
		setErrors(next);
		if (next.client || next.from || next.rate) return;

		let sent: BillingTerm[];
		if (mode.kind === "attach" && term) sent = [term];
		else if (mode.kind === "term" && term) {
			sent = sortTerms(editing ? terms.map((t) => (t === editing ? term : t)) : [...terms, term]);
		} else sent = terms;
		const edited = term ? sent.indexOf(term) : undefined;
		const input = { clientId: client?.id ?? billing?.clientId ?? "", terms: sent };

		setBusy(true);
		try {
			const saved = await withPastConsent(
				(rewritePast) => setBilling.mutateAsync({ projectId: project.id, input, rewritePast }),
				(detail) =>
					confirm({
						title: "Change a month already over?",
						detail,
						confirmLabel: "Change it",
						cancelLabel: "Keep it",
					}),
			);
			if (saved === undefined) return;
			toast.success(
				mode.kind === "attach"
					? `${project.name} is billed to ${client?.name ?? "the client"}`
					: "Billing saved",
			);
			onClose();
		} catch (err) {
			setErrors(billingErrors(err, edited === -1 ? undefined : edited));
		} finally {
			setBusy(false);
		}
	};

	const addClient = async (input: ClientInput): Promise<boolean> => {
		const created = await createClient.mutateAsync(input);
		setClientId(created.id);
		toast.success(`${created.name} added`);
		return true;
	};

	const close = () => {
		if (!busy) onClose();
	};

	const title =
		mode.kind === "attach"
			? "Bill this project"
			: mode.kind === "client"
				? "Change client"
				: editing
					? "Edit billing"
					: "Change billing from…";
	const description =
		mode.kind === "attach"
			? "Who the work is for, from when, and at whose rate."
			: mode.kind === "client"
				? "Every hour of the project moves with it, past months included."
				: "From this day on, until the next change.";

	return (
		<Dialog
			open
			onClose={close}
			returnFocus={returnFocus}
			title={title}
			description={description}
			contentClassName="sm:w-full sm:max-w-[440px]"
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					void save();
				}}
				noValidate
				className="space-y-3.5"
			>
				{asksClient && (
					<div>
						<label htmlFor={`${id}-client`} className={cn(LABEL, "block mb-[5px]")}>
							Client
						</label>
						<select
							id={`${id}-client`}
							value={clientId}
							onChange={(e) => {
								if (e.target.value === NEW_CLIENT) setAddingClient(true);
								else setClientId(e.target.value);
							}}
							autoFocus
							aria-invalid={errors.client ? true : undefined}
							aria-describedby={errors.client ? `${id}-client-error` : undefined}
							className={FIELD}
						>
							<option value="">Choose a client…</option>
							{/* An archived client stays listed while it is the one billed. */}
							{client?.archived && (
								<option value={client.id}>
									{client.name} · {client.currency} · archived
								</option>
							)}
							{clients.map((c) => (
								<option key={c.id} value={c.id}>
									{c.name} · {c.currency}
								</option>
							))}
							<option value={NEW_CLIENT}>New client…</option>
						</select>
						{errors.client && (
							<p id={`${id}-client-error`} className={ERROR}>
								{errors.client}
							</p>
						)}
					</div>
				)}

				{asksFrom && (
					<div>
						<label htmlFor={`${id}-from`} className={cn(LABEL, "block mb-[5px]")}>
							{mode.kind === "attach" ? "Billable from" : "From"}
						</label>
						<input
							id={`${id}-from`}
							type="date"
							value={from}
							onChange={(e) => setFrom(e.target.value)}
							autoFocus={mode.kind === "term"}
							aria-invalid={errors.from ? true : undefined}
							aria-describedby={
								[fromHint ? `${id}-from-hint` : null, errors.from ? `${id}-from-error` : null]
									.filter(Boolean)
									.join(" ") || undefined
							}
							className={cn(FIELD, "font-mono font-bold")}
						/>
						{fromHint && (
							<p id={`${id}-from-hint`} className="mt-1 text-xs text-muted-foreground font-medium">
								{fromHint}
								{parseIsoDate(from) ? ` · ${longDate(from)}` : ""}
							</p>
						)}
						{mode.kind === "term" && !from && (
							<div className="mt-2 flex flex-wrap gap-1.5">
								{chips.map(([label, iso]) => (
									<button key={label} type="button" onClick={() => setFrom(iso)} className={CHIP}>
										{label}
									</button>
								))}
							</div>
						)}
						{errors.from && (
							<p id={`${id}-from-error`} className={ERROR}>
								{errors.from}
							</p>
						)}
					</div>
				)}

				{mode.kind === "term" && (
					<fieldset className="min-w-0 border-0 p-0 m-0">
						<legend className={cn(LABEL, "mb-[5px]")}>Its hours are</legend>
						<div className="inline-flex gap-1 p-1 rounded-full bg-secondary">
							{[true, false].map((value) => (
								<button
									key={String(value)}
									type="button"
									aria-pressed={billable === value}
									onClick={() => setBillable(value)}
									className={cn(
										SEGMENT,
										billable === value
											? "bg-accent text-accent-foreground"
											: "text-muted-foreground",
									)}
								>
									{value ? "Billable" : "Not billable"}
								</button>
							))}
						</div>
					</fieldset>
				)}

				{asksRate && (
					<fieldset className="min-w-0 border-0 p-0 m-0">
						<legend className={cn(LABEL, "mb-[5px]")}>Rate</legend>
						<label className="flex items-center gap-2 text-[13px] font-medium text-foreground">
							<input
								type="radio"
								name={`${id}-rate`}
								checked={!ownRate}
								onChange={() => setOwnRate(false)}
								className="accent-[hsl(var(--accent))]"
							/>
							Client's rate
							<span className="text-muted-foreground">
								(
								{client
									? clientRate
										? formatRate(clientRate.rateMinor, client.currency, client.minorUnits)
										: "none yet"
									: "choose a client"}
								)
							</span>
						</label>
						<div className="mt-2 flex items-center gap-2 text-[13px] font-medium text-foreground">
							<label className="flex items-center gap-2">
								<input
									type="radio"
									name={`${id}-rate`}
									checked={ownRate}
									onChange={() => setOwnRate(true)}
									className="accent-[hsl(var(--accent))]"
								/>
								Its own rate
							</label>
							<input
								type="text"
								inputMode="decimal"
								value={amount}
								onChange={(e) => {
									setAmount(e.target.value);
									setOwnRate(true);
								}}
								aria-label="Its own rate, per hour"
								placeholder="95.00"
								aria-invalid={errors.rate ? true : undefined}
								aria-describedby={errors.rate ? `${id}-rate-error` : undefined}
								className={cn(FIELD, "w-28 font-mono font-bold")}
							/>
							<span className="text-muted-foreground font-bold">
								{client?.currency ?? billing?.currency ?? ""} /h
							</span>
						</div>
						{errors.rate && (
							<p id={`${id}-rate-error`} className={ERROR}>
								{errors.rate}
							</p>
						)}
					</fieldset>
				)}

				{errors.general.length > 0 && (
					<div className="text-sm text-destructive-ink space-y-0.5" role="alert">
						{errors.general.map((message) => (
							<p key={message}>{message}</p>
						))}
					</div>
				)}

				<div className="flex justify-end gap-2.5 pt-1">
					<Button type="button" variant="secondary" size="sm" onClick={close} disabled={busy}>
						Cancel
					</Button>
					<Button type="submit" size="sm" disabled={busy}>
						{busy ? "Saving…" : mode.kind === "attach" ? "Bill it" : "Save"}
					</Button>
				</div>
			</form>

			{addingClient && (
				<ClientDialog
					todayIso={todayIso}
					onSave={addClient}
					onClose={() => setAddingClient(false)}
				/>
			)}
			{confirmDialog}
		</Dialog>
	);
}
