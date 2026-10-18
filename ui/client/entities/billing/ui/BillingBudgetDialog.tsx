/**
 * BillingBudgetDialog — a client's or a billed project's billing budget, in
 * one column (docs/billing.md, phase 1b): measured in hours or in money (the
 * client's one currency, named and never chosen here), the limit, whether
 * it resets every month or counts in total from a day, and the percent to
 * warn at. 100 % is always the second threshold.
 *
 * A total's first day is picked, never filled in for the user: "When billing
 * started", the scope's earliest billing term, is preselected and in view,
 * beside the 1st of this month, today and the calendar. The limit is read
 * off the typed text (`parseHours`, `parseMoney`), never through a float.
 *
 * Every key is sent: the other unit's limit and a monthly budget's start go
 * as null. A 422's `fields` land on their inputs, and a 409 shows in the
 * API's words. A budget write is not gated: it changes no billable figure.
 */

import { useId, useState } from "react";
import { toast } from "sonner";
import { apiFieldErrors, describeError } from "@/shared/api";
import {
	BILLING_BUDGET_MINOR_MAX,
	cn,
	formatDateShort,
	minorToInput,
	parseHours,
	parseIsoDate,
	parseMoney,
} from "@/shared/lib";
import { Button, Dialog } from "@/shared/ui";
import { useRemoveBillingBudget, useSetBillingBudget } from "../api";
import type {
	BillingBudget,
	BillingBudgetInput,
	BillingBudgetPeriod,
	BillingBudgetScope,
	BillingBudgetUnit,
} from "../model";

export interface BillingBudgetDialogProps {
	scope: BillingBudgetScope;
	scopeId: string;
	/** The client's name, or the project's. */
	name: string;
	/** The scope's client's currency, which a money limit is in. */
	currency: string;
	minorUnits: number;
	/** The budget the scope has; a new one without it. */
	budget?: BillingBudget;
	/** The earliest term of the scope's billing, across a client's projects: "When billing started". */
	billingStartedOn?: string;
	todayIso: string;
	onClose: () => void;
	/** Where focus goes on close when the control that opened the dialog has gone. */
	returnFocus?: () => HTMLElement | null | undefined;
}

interface Errors {
	amount?: string;
	startsOn?: string;
	warn?: string;
	general: string[];
}

const LABEL =
	"block font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground mb-[5px]";
const FIELD =
	"w-full min-w-0 bg-secondary border-0 rounded-xl text-foreground px-3 py-2 text-[13.5px] font-medium placeholder:text-muted-foreground focus:outline-hidden focus:ring-[3px] focus:ring-accent aria-invalid:ring-2 aria-invalid:ring-destructive/60 disabled:opacity-60";
const ERROR = "mt-1 text-xs text-destructive-ink";
const HINT = "mt-1 text-xs text-muted-foreground font-medium";
const CHIP =
	"inline-flex items-center rounded-full px-2.5 py-0.5 text-[11.5px] font-bold transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";
const SEGMENT =
	"px-[13px] py-[5px] rounded-full text-[12.5px] font-bold transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

/** "Euro", or the code where the browser has no name for it. */
function currencyName(code: string): string {
	try {
		return new Intl.DisplayNames("en-US", { type: "currency" }).of(code) ?? code;
	} catch {
		return code;
	}
}

function shortDay(iso: string): string {
	const d = parseIsoDate(iso);
	return d ? formatDateShort(d) : iso;
}

/** "40", "37.5": the API's hours as the field starts. */
function hoursToInput(hours: number): string {
	return String(Number(hours.toFixed(2)));
}

/** A whole percent from 1 to 99, typed. */
function parseWarn(text: string): number | undefined {
	const trimmed = text.trim();
	if (!/^\d{1,2}$/.test(trimmed)) return undefined;
	const value = Number(trimmed);
	return value >= 1 && value <= 99 ? value : undefined;
}

/** A refused save, onto the inputs: a 422's paths are the body's keys. */
function budgetErrors(err: unknown): Errors {
	const out: Errors = { general: [] };
	const fields = apiFieldErrors(err);
	if (Object.keys(fields).length === 0) {
		out.general.push(describeError(err, "Failed to save the budget"));
		return out;
	}
	for (const [path, message] of Object.entries(fields)) {
		if ((path === "limit_hours" || path === "limit_minor") && !out.amount) out.amount = message;
		else if (path === "starts_on" && !out.startsOn) out.startsOn = message;
		else if (path === "warn_at_percent" && !out.warn) out.warn = message;
		else out.general.push(path ? `${path}: ${message}` : message);
	}
	return out;
}

function SegmentGroup<V extends string>({
	legend,
	value,
	options,
	onChange,
}: {
	legend: string;
	value: V;
	options: [V, string][];
	onChange: (value: V) => void;
}) {
	return (
		<fieldset className="min-w-0 border-0 p-0 m-0">
			<legend className={LABEL}>{legend}</legend>
			<div className="inline-flex flex-wrap gap-1 p-1 rounded-[1.25rem] bg-secondary">
				{options.map(([option, label]) => (
					<button
						key={option}
						type="button"
						aria-pressed={value === option}
						onClick={() => onChange(option)}
						className={cn(
							SEGMENT,
							value === option ? "bg-accent text-accent-foreground" : "text-muted-foreground",
						)}
					>
						{label}
					</button>
				))}
			</div>
		</fieldset>
	);
}

export function BillingBudgetDialog({
	scope,
	scopeId,
	name,
	currency,
	minorUnits,
	budget,
	billingStartedOn,
	todayIso,
	onClose,
	returnFocus,
}: BillingBudgetDialogProps) {
	const id = useId();
	const setBudget = useSetBillingBudget();
	const removeBudget = useRemoveBillingBudget();

	const firstOfMonth = `${todayIso.slice(0, 7)}-01`;
	const [unit, setUnit] = useState<BillingBudgetUnit>(budget?.unit ?? "hours");
	// One field per unit, so switching back finds what was typed there.
	const [hours, setHours] = useState(
		budget?.limitHours !== undefined ? hoursToInput(budget.limitHours) : "",
	);
	const [money, setMoney] = useState(
		budget?.limitMinor !== undefined ? minorToInput(budget.limitMinor, minorUnits) : "",
	);
	const [period, setPeriod] = useState<BillingBudgetPeriod>(
		budget?.period ?? (scope === "client" ? "monthly" : "total"),
	);
	const [startsOn, setStartsOn] = useState(budget?.startsOn ?? billingStartedOn ?? firstOfMonth);
	const [warn, setWarn] = useState(String(budget?.warnAtPercent ?? 80));
	const [errors, setErrors] = useState<Errors>({ general: [] });
	const busy = setBudget.isPending || removeBudget.isPending;

	const chips: [string, string][] = [
		...(billingStartedOn
			? [
					[`When billing started (${shortDay(billingStartedOn)})`, billingStartedOn] as [
						string,
						string,
					],
				]
			: []),
		["1st of this month", firstOfMonth],
		["Today", todayIso],
	];

	const save = async () => {
		const next: Errors = { general: [] };
		let limitHours: number | undefined;
		let limitMinor: number | undefined;
		if (unit === "hours") {
			const parsed = parseHours(hours);
			if (parsed.ok) limitHours = parsed.hundredths / 100;
			else next.amount = parsed.reason;
		} else {
			const parsed = parseMoney(money, minorUnits, BILLING_BUDGET_MINOR_MAX);
			if (parsed.ok) limitMinor = parsed.minor;
			else next.amount = parsed.reason;
		}
		if (period === "total" && !parseIsoDate(startsOn))
			next.startsOn = "Pick the day it counts from.";
		const warnAtPercent = parseWarn(warn);
		if (warnAtPercent === undefined) next.warn = "A whole percent from 1 to 99.";
		setErrors(next);
		if (next.amount || next.startsOn || warnAtPercent === undefined) return;

		const input: BillingBudgetInput = {
			unit,
			period,
			limitHours,
			limitMinor,
			startsOn: period === "total" ? startsOn : undefined,
			warnAtPercent,
		};
		try {
			await setBudget.mutateAsync({ scope, scopeId, input });
			toast.success("Budget saved");
			onClose();
		} catch (err) {
			setErrors(budgetErrors(err));
		}
	};

	const remove = async () => {
		try {
			await removeBudget.mutateAsync({ scope, scopeId });
			toast.success("Budget removed");
			onClose();
		} catch (err) {
			setErrors({ general: [describeError(err, "Failed to remove the budget")] });
		}
	};

	const close = () => {
		if (!busy) onClose();
	};

	const amountId = `${id}-amount`;
	const warnId = `${id}-warn`;
	const fromId = `${id}-from`;

	return (
		<Dialog
			open
			onClose={close}
			returnFocus={returnFocus}
			title={`${name}'s budget`}
			description={
				scope === "client"
					? `Counts the billable hours of every project billed to ${name}.`
					: `Counts ${name}'s billable hours only.`
			}
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
				<div>
					<SegmentGroup
						legend="Measure in"
						value={unit}
						options={[
							["hours", "Hours"],
							["money", `Money (${currency})`],
						]}
						onChange={setUnit}
					/>
					{unit === "money" && (
						<p className={HINT}>In {currencyName(currency)}, the client's currency.</p>
					)}
				</div>

				<div>
					<label htmlFor={amountId} className={LABEL}>
						Budget
					</label>
					<div className="flex items-center gap-2">
						<input
							id={amountId}
							type="text"
							inputMode="decimal"
							value={unit === "hours" ? hours : money}
							onChange={(e) => (unit === "hours" ? setHours : setMoney)(e.target.value)}
							placeholder={unit === "hours" ? "40" : minorToInput(100000, minorUnits)}
							autoFocus
							aria-invalid={errors.amount ? true : undefined}
							aria-describedby={errors.amount ? `${amountId}-error` : undefined}
							className={cn(FIELD, "w-36 font-mono font-bold")}
						/>
						<span className="text-muted-foreground font-bold text-[13px]">
							{unit === "hours" ? "h" : currency}
						</span>
					</div>
					{errors.amount && (
						<p id={`${amountId}-error`} className={ERROR}>
							{errors.amount}
						</p>
					)}
				</div>

				<SegmentGroup
					legend="Resets"
					value={period}
					options={[
						["monthly", "Every month"],
						["total", "In total"],
					]}
					onChange={setPeriod}
				/>

				{period === "total" && (
					<div>
						<label htmlFor={fromId} className={LABEL}>
							From
						</label>
						<div className="flex flex-wrap gap-1.5 mb-2">
							{chips.map(([label, iso]) => (
								<button
									key={label}
									type="button"
									aria-pressed={startsOn === iso}
									onClick={() => setStartsOn(iso)}
									className={cn(
										CHIP,
										startsOn === iso
											? "bg-accent text-accent-foreground"
											: "bg-secondary text-foreground hover:bg-sidebar-accent",
									)}
								>
									{label}
								</button>
							))}
						</div>
						<input
							id={fromId}
							type="date"
							value={startsOn}
							onChange={(e) => setStartsOn(e.target.value)}
							aria-invalid={errors.startsOn ? true : undefined}
							aria-describedby={`${fromId}-hint${errors.startsOn ? ` ${fromId}-error` : ""}`}
							className={cn(FIELD, "w-44 font-mono font-bold")}
						/>
						<p id={`${fromId}-hint`} className={HINT}>
							Counts from this day on, with no end.
						</p>
						{errors.startsOn && (
							<p id={`${fromId}-error`} className={ERROR}>
								{errors.startsOn}
							</p>
						)}
					</div>
				)}

				<div>
					<label htmlFor={warnId} className={LABEL}>
						Warn me at
					</label>
					<div className="flex items-center gap-2 flex-wrap">
						<input
							id={warnId}
							type="text"
							inputMode="numeric"
							value={warn}
							onChange={(e) => setWarn(e.target.value)}
							aria-invalid={errors.warn ? true : undefined}
							aria-describedby={`${warnId}-suffix${errors.warn ? ` ${warnId}-error` : ""}`}
							className={cn(FIELD, "w-16 font-mono font-bold")}
						/>
						<span id={`${warnId}-suffix`} className="text-[13px] font-medium text-muted-foreground">
							% — and again when it's used up
						</span>
					</div>
					{errors.warn && (
						<p id={`${warnId}-error`} className={ERROR}>
							{errors.warn}
						</p>
					)}
				</div>

				{errors.general.length > 0 && (
					<div className="text-sm text-destructive-ink space-y-0.5" role="alert">
						{errors.general.map((message) => (
							<p key={message}>{message}</p>
						))}
					</div>
				)}

				<div className="flex items-center flex-wrap justify-end gap-2.5 pt-1">
					{budget && (
						<Button
							type="button"
							variant="ghost"
							size="sm"
							className="mr-auto text-destructive-ink"
							onClick={() => void remove()}
							disabled={busy}
						>
							Remove budget
						</Button>
					)}
					<Button type="button" variant="secondary" size="sm" onClick={close} disabled={busy}>
						Cancel
					</Button>
					<Button type="submit" size="sm" disabled={busy}>
						{setBudget.isPending ? "Saving…" : "Save"}
					</Button>
				</div>
			</form>
		</Dialog>
	);
}
