/**
 * ClientDialog — a client's record: its name, an optional contact, its one
 * currency and its dated default rate (docs/billing.md). Opened on the
 * Clients page to add or edit one, and from a project's billing dialog to
 * add one in passing.
 *
 * The currency starts unchosen: a client in the wrong currency is a typo
 * the user would not see until the first invoice, and once anything is
 * priced in it (`currencyLocked`) it can no longer change. The rate is a
 * register of rows "From [day] [amount] /h", and a row's day is picked —
 * with a chip or the calendar — never filled in for the user, since it
 * decides which month's figures the rate moves. Amounts are read off the
 * typed text (`parseMoney`), never through a float.
 *
 * The host does the write (`onSave`): a new client is a plain create, an
 * edit goes through `withPastConsent`, which asks before a change to a
 * month already over and resolves false when the user declines. A refusal
 * comes back here and lands on the input it names: a 422's `fields`, an
 * unknown or locked currency on the currency.
 */

import { Plus, Trash2 } from "lucide-react";
import { useId, useState } from "react";
import { ApiError, apiFieldErrors, describeError } from "@/shared/api";
import {
	addIsoDays,
	cn,
	formatDateShort,
	minorToInput,
	parseIsoDate,
	parseMoney,
} from "@/shared/lib";
import { Button, Dialog } from "@/shared/ui";
import { useCurrencies } from "../api";
import type { Client, ClientInput, Currency } from "../model";

export interface ClientDialogProps {
	/** The client to edit; a new one without it. */
	client?: Client;
	todayIso: string;
	/**
	 * Writes the client. Resolves true once it is saved, false when nothing
	 * was written because the user declined a question it asked; a refusal is
	 * thrown, and shown on the inputs.
	 */
	onSave: (input: ClientInput) => Promise<boolean>;
	onClose: () => void;
	/** Where focus goes on close when the control that opened the dialog has gone. */
	returnFocus?: () => HTMLElement | null | undefined;
}

interface RateRow {
	/** Stable across edits, so a row keeps its inputs while the dates are re-sorted. */
	key: number;
	effectiveFrom: string;
	amount: string;
}

interface RateRowErrors {
	effectiveFrom?: string;
	amount?: string;
}

interface ClientFormErrors {
	name?: string;
	contactName?: string;
	contactEmail?: string;
	currency?: string;
	/** About the register as a whole: the order, a day twice. */
	rates?: string;
	/** By row key. */
	rows: Record<number, RateRowErrors>;
	/** Messages with no input to sit beside. */
	general: string[];
}

const FIELD =
	"w-full min-w-0 bg-secondary border-0 rounded-xl text-foreground px-3 py-2 text-[13.5px] font-medium placeholder:text-muted-foreground focus:outline-hidden focus:ring-[3px] focus:ring-accent aria-invalid:ring-2 aria-invalid:ring-destructive/60 disabled:opacity-60";
const LABEL =
	"block font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground mb-[5px]";
const ERROR = "mt-1 text-xs text-destructive-ink";
const CHIP =
	"inline-flex items-center rounded-full bg-secondary px-2.5 py-0.5 text-[11.5px] font-bold text-foreground hover:bg-sidebar-accent transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

const TOP_LEVEL: Record<string, keyof Omit<ClientFormErrors, "rows" | "general">> = {
	name: "name",
	contact_name: "contactName",
	contact_email: "contactEmail",
	currency: "currency",
	rates: "rates",
};

/** The codes whose refusal is about the currency picked. */
const CURRENCY_CODES = new Set(["UNKNOWN_CURRENCY", "CURRENCY_IN_USE"]);

function emptyErrors(): ClientFormErrors {
	return { rows: {}, general: [] };
}

function hasErrors(errors: ClientFormErrors): boolean {
	const { rows, general, ...flat } = errors;
	return (
		general.length > 0 ||
		Object.values(rows).some((row) => row.effectiveFrom || row.amount) ||
		Object.values(flat).some((v) => v !== undefined)
	);
}

/**
 * A refused save, sorted onto the inputs. A 422's paths are the body's —
 * `name`, `rates.1.rate_minor` — and `rates` went out in `sent` order, so a
 * row's index is its place there. An unknown or locked currency is the
 * currency's. Anything else is a general message.
 */
function clientFormErrors(err: unknown, sent: readonly RateRow[]): ClientFormErrors {
	const out = emptyErrors();
	const fields = apiFieldErrors(err);
	if (Object.keys(fields).length === 0) {
		if (err instanceof ApiError && err.code && CURRENCY_CODES.has(err.code)) {
			out.currency = err.message;
		} else {
			out.general.push(describeError(err, "Failed to save the client"));
		}
		return out;
	}
	for (const [path, message] of Object.entries(fields)) {
		const [head, index, leaf] = path.split(".");
		const row = head === "rates" && index !== undefined ? sent[Number(index)] : undefined;
		if (row && (leaf === "rate_minor" || leaf === "effective_from")) {
			const key = leaf === "rate_minor" ? "amount" : "effectiveFrom";
			out.rows[row.key] = { ...out.rows[row.key], [key]: message };
			continue;
		}
		const field = TOP_LEVEL[head];
		if (field && out[field] === undefined) out[field] = message;
		else out.general.push(path ? `${path}: ${message}` : message);
	}
	return out;
}

function firstOfMonth(iso: string): string {
	return `${iso.slice(0, 7)}-01`;
}

/** The 1st of the month after the one `iso` falls in. */
function firstOfNextMonth(iso: string): string {
	return `${addIsoDays(firstOfMonth(iso), 32).slice(0, 7)}-01`;
}

function currencyName(code: string): string {
	try {
		return new Intl.DisplayNames(["en"], { type: "currency" }).of(code) ?? code;
	} catch {
		return code;
	}
}

export function ClientDialog({
	client,
	todayIso,
	onSave,
	onClose,
	returnFocus,
}: ClientDialogProps) {
	const id = useId();
	const { data: currencies } = useCurrencies();
	const [name, setName] = useState(client?.name ?? "");
	const [contactName, setContactName] = useState(client?.contactName ?? "");
	const [contactEmail, setContactEmail] = useState(client?.contactEmail ?? "");
	const [currency, setCurrency] = useState(client?.currency ?? "");
	const [rows, setRows] = useState<RateRow[]>(() =>
		(client?.rates ?? []).map((rate, key) => ({
			key,
			effectiveFrom: rate.effectiveFrom,
			amount: minorToInput(rate.rateMinor, client?.minorUnits ?? 2),
		})),
	);
	const [nextKey, setNextKey] = useState(rows.length);
	const [errors, setErrors] = useState<ClientFormErrors>(emptyErrors);
	const [busy, setBusy] = useState(false);

	const locked = client?.currencyLocked ?? false;
	// The client's own currency is always selectable: before the table
	// arrives, and after it when the code has been withdrawn since it was
	// chosen, which the API still reads but no longer lists.
	const table = currencies ?? [];
	const options: Currency[] =
		client && !table.some((c) => c.code === client.currency)
			? [{ code: client.currency, minorUnits: client.minorUnits }, ...table]
			: table;
	const chosen = options.find((c) => c.code === currency);
	const minorUnits = chosen?.minorUnits ?? (currency === client?.currency ? client.minorUnits : 2);
	const chips: [string, string][] = [
		["1st of this month", firstOfMonth(todayIso)],
		["Today", todayIso],
		["1st of next month", firstOfNextMonth(todayIso)],
	];

	const setRow = (key: number, patch: Partial<RateRow>) =>
		setRows((all) => all.map((row) => (row.key === key ? { ...row, ...patch } : row)));

	const addRow = () => {
		setRows((all) => [...all, { key: nextKey, effectiveFrom: "", amount: "" }]);
		setNextKey((k) => k + 1);
	};

	const validate = (): {
		errors: ClientFormErrors;
		rates: ClientInput["rates"];
		sent: RateRow[];
	} => {
		const next = emptyErrors();
		if (!name.trim()) next.name = "A client needs a name.";
		if (!currency) next.currency = "Choose the currency the client is billed in.";
		const rates: ClientInput["rates"] = [];
		const sent = [...rows].sort((a, b) => a.effectiveFrom.localeCompare(b.effectiveFrom));
		const seen = new Set<string>();
		for (const row of sent) {
			const rowErrors: RateRowErrors = {};
			if (!parseIsoDate(row.effectiveFrom)) rowErrors.effectiveFrom = "Pick the day it starts.";
			else if (seen.has(row.effectiveFrom)) {
				rowErrors.effectiveFrom = "Another rate starts on this day.";
			}
			seen.add(row.effectiveFrom);
			const parsed = parseMoney(row.amount, minorUnits);
			if (!parsed.ok) rowErrors.amount = parsed.reason;
			if (rowErrors.effectiveFrom || rowErrors.amount) next.rows[row.key] = rowErrors;
			else if (parsed.ok) rates.push({ effectiveFrom: row.effectiveFrom, rateMinor: parsed.minor });
		}
		return { errors: next, rates, sent };
	};

	const save = async () => {
		const { errors: found, rates, sent } = validate();
		setErrors(found);
		if (hasErrors(found)) return;
		setBusy(true);
		try {
			const saved = await onSave({
				name,
				contactName,
				contactEmail,
				currency,
				rates,
			});
			if (saved) onClose();
		} catch (err) {
			setErrors(clientFormErrors(err, sent));
		} finally {
			setBusy(false);
		}
	};

	const close = () => {
		if (!busy) onClose();
	};

	const describedBy = (field: string, error: string | undefined) =>
		error ? `${id}-${field}-error` : undefined;

	return (
		<Dialog
			open
			onClose={close}
			returnFocus={returnFocus}
			title={client ? "Edit client" : "New client"}
			description="Who you bill: a contact if you want one, the currency, and the rate an hour."
			contentClassName="sm:w-full sm:max-w-[460px]"
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					void save();
				}}
				noValidate
				className="space-y-3"
			>
				<div>
					<label htmlFor={`${id}-name`} className={LABEL}>
						Name
					</label>
					<input
						id={`${id}-name`}
						type="text"
						value={name}
						onChange={(e) => setName(e.target.value)}
						autoFocus
						maxLength={120}
						aria-invalid={errors.name ? true : undefined}
						aria-describedby={describedBy("name", errors.name)}
						className={FIELD}
					/>
					{errors.name && (
						<p id={`${id}-name-error`} className={ERROR}>
							{errors.name}
						</p>
					)}
				</div>

				<div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
					<div>
						<label htmlFor={`${id}-contact`} className={LABEL}>
							Contact
						</label>
						<input
							id={`${id}-contact`}
							type="text"
							value={contactName}
							onChange={(e) => setContactName(e.target.value)}
							placeholder="Optional"
							maxLength={120}
							aria-invalid={errors.contactName ? true : undefined}
							aria-describedby={describedBy("contact", errors.contactName)}
							className={FIELD}
						/>
						{errors.contactName && (
							<p id={`${id}-contact-error`} className={ERROR}>
								{errors.contactName}
							</p>
						)}
					</div>
					<div>
						<label htmlFor={`${id}-email`} className={LABEL}>
							Contact email
						</label>
						<input
							id={`${id}-email`}
							type="email"
							value={contactEmail}
							onChange={(e) => setContactEmail(e.target.value)}
							placeholder="Optional · shown, never mailed"
							maxLength={254}
							aria-invalid={errors.contactEmail ? true : undefined}
							aria-describedby={describedBy("email", errors.contactEmail)}
							className={FIELD}
						/>
						{errors.contactEmail && (
							<p id={`${id}-email-error`} className={ERROR}>
								{errors.contactEmail}
							</p>
						)}
					</div>
				</div>

				<div>
					<label htmlFor={`${id}-currency`} className={LABEL}>
						Currency
					</label>
					<select
						id={`${id}-currency`}
						value={currency}
						onChange={(e) => setCurrency(e.target.value)}
						disabled={locked}
						aria-invalid={errors.currency ? true : undefined}
						aria-describedby={
							[locked ? `${id}-currency-hint` : null, describedBy("currency", errors.currency)]
								.filter(Boolean)
								.join(" ") || undefined
						}
						className={FIELD}
					>
						<option value="">Choose a currency…</option>
						{options.map((c) => (
							<option key={c.code} value={c.code}>
								{c.code} — {currencyName(c.code)}
							</option>
						))}
					</select>
					{locked && (
						<p id={`${id}-currency-hint`} className="mt-1 text-xs text-muted-foreground">
							Something is already priced in {client?.currency}, so it stays.
						</p>
					)}
					{errors.currency && (
						<p id={`${id}-currency-error`} className={ERROR}>
							{errors.currency}
						</p>
					)}
				</div>

				<fieldset className="min-w-0 border-0 p-0 m-0">
					<legend className={LABEL}>Default rate</legend>
					{rows.length === 0 ? (
						<p className="text-[12.5px] text-muted-foreground font-medium">
							No default rate: a project's hours are priced only by a rate of its own.
						</p>
					) : (
						<ul className="flex flex-col gap-2.5">
							{rows.map((row) => {
								const rowErrors = errors.rows[row.key] ?? {};
								const picked = parseIsoDate(row.effectiveFrom);
								return (
									<li key={row.key} className="rounded-[18px] bg-secondary/60 p-2.5">
										<div className="flex flex-wrap items-center gap-2 text-[12.5px] font-bold">
											<label htmlFor={`${id}-from-${row.key}`} className="text-muted-foreground">
												From
											</label>
											<input
												id={`${id}-from-${row.key}`}
												type="date"
												value={row.effectiveFrom}
												onChange={(e) => setRow(row.key, { effectiveFrom: e.target.value })}
												aria-invalid={rowErrors.effectiveFrom ? true : undefined}
												aria-describedby={
													rowErrors.effectiveFrom ? `${id}-from-${row.key}-error` : undefined
												}
												className={cn(FIELD, "w-auto font-mono font-bold bg-card")}
											/>
											<input
												type="text"
												inputMode="decimal"
												value={row.amount}
												onChange={(e) => setRow(row.key, { amount: e.target.value })}
												aria-label={`Rate from ${picked ? formatDateShort(picked) : "the day picked"}, per hour`}
												placeholder="85.00"
												aria-invalid={rowErrors.amount ? true : undefined}
												aria-describedby={
													rowErrors.amount ? `${id}-amount-${row.key}-error` : undefined
												}
												className={cn(FIELD, "w-28 font-mono font-bold bg-card")}
											/>
											<span className="text-muted-foreground">
												{currency ? `${currency} /h` : "/h"}
											</span>
											<button
												type="button"
												onClick={() => setRows((all) => all.filter((r) => r.key !== row.key))}
												aria-label={`Remove the rate from ${picked ? formatDateShort(picked) : "an unpicked day"}`}
												className="ml-auto grid place-items-center w-7 h-7 rounded-full text-muted-foreground hover:bg-sidebar-accent hover:text-destructive-ink transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
											>
												<Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
											</button>
										</div>
										{!row.effectiveFrom && (
											<div className="mt-2 flex flex-wrap gap-1.5">
												{chips.map(([label, iso]) => (
													<button
														key={label}
														type="button"
														onClick={() => setRow(row.key, { effectiveFrom: iso })}
														className={CHIP}
													>
														{label}
													</button>
												))}
											</div>
										)}
										{rowErrors.effectiveFrom && (
											<p id={`${id}-from-${row.key}-error`} className={ERROR}>
												{rowErrors.effectiveFrom}
											</p>
										)}
										{rowErrors.amount && (
											<p id={`${id}-amount-${row.key}-error`} className={ERROR}>
												{rowErrors.amount}
											</p>
										)}
									</li>
								);
							})}
						</ul>
					)}
					{errors.rates && <p className={ERROR}>{errors.rates}</p>}
					<button
						type="button"
						onClick={addRow}
						className="mt-2 inline-flex items-center gap-1 text-accent-ink text-[12.5px] font-bold hover:underline underline-offset-[3px] rounded-full focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
					>
						<Plus className="w-3 h-3" aria-hidden="true" />
						{rows.length === 0 ? "Add a rate" : "Change the rate from…"}
					</button>
				</fieldset>

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
						{busy ? "Saving…" : client ? "Save" : "Add client"}
					</Button>
				</div>
			</form>
		</Dialog>
	);
}
