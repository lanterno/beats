/**
 * ContractTermFields — the inputs for one contract term: schedule type,
 * the numbers that type needs, the day it takes effect, a note. Shared by
 * ProjectForm (a new day job's first term) and the contract history
 * panel's term dialog, so a term is described the same way wherever it
 * is typed.
 *
 * Controlled: the host owns the values and the errors. Percentage is a
 * percent here (80) and a fraction on the wire — `termFromForm` converts.
 */

import { BadgeCheck, Clock3, Scale, Target } from "lucide-react";
import { useId } from "react";
import type { ScheduleType } from "../model";
import {
	describeTerm,
	SCHEDULE_TYPE_LABELS,
	type TermFieldErrors,
	type TermFormValues,
	termFromForm,
	termHoursPerDay,
	termHoursPerWeek,
	validateTerm,
} from "../model";

export interface ContractTermFieldsProps {
	values: TermFormValues;
	onChange: (next: TermFormValues) => void;
	errors?: TermFieldErrors;
	/** Label for the effective-from input: "Effective from" on a first term, "Change from" on a later one. */
	dateLabel?: string;
	/** Whether to offer the free-text note. Off in the project form, where the section is long already. */
	withNote?: boolean;
	autoFocusField?: keyof TermFormValues;
}

const SCHEDULE_OPTIONS: {
	value: ScheduleType;
	description: string;
	Icon: typeof Target;
}[] = [
	{ value: "full_time", description: "100% of a full-time week", Icon: BadgeCheck },
	{ value: "part_time", description: "A percentage of a full-time week", Icon: Scale },
	{ value: "custom", description: "A fixed number of hours a week", Icon: Clock3 },
	{ value: "objective", description: "No hours owed; a personal goal if you like", Icon: Target },
];

const inputCls =
	"w-full rounded-md border border-input bg-background py-2 px-3 text-base text-foreground focus:outline-hidden focus:ring-2 focus:ring-accent/20 focus:border-accent/40 aria-invalid:border-destructive/60";
const labelCls = "block text-muted-foreground text-xs uppercase tracking-[0.12em] mb-1.5";
const errorCls = "mt-1 text-xs text-destructive";

export function ContractTermFields({
	values,
	onChange,
	errors = {},
	dateLabel = "Effective from",
	withNote = false,
	autoFocusField,
}: ContractTermFieldsProps) {
	const id = useId();
	const set = <K extends keyof TermFormValues>(k: K, v: TermFormValues[K]) =>
		onChange({ ...values, [k]: v });

	const timeBased = values.scheduleType === "full_time" || values.scheduleType === "part_time";
	// A live preview of what the numbers add up to, once they are complete.
	const preview = (() => {
		if (values.scheduleType === "objective") return null;
		if (Object.keys(validateTerm(values)).length > 0) return null;
		const term = termFromForm(values);
		const weekly = termHoursPerWeek(term);
		const daily = termHoursPerDay(term);
		if (weekly == null || daily == null) return null;
		return `${describeTerm(term)} · ${daily} h/day`;
	})();

	return (
		<div className="space-y-3">
			<fieldset>
				<legend id={`${id}-schedule`} className={labelCls}>
					Schedule
				</legend>
				<div
					className="grid grid-cols-1 sm:grid-cols-2 gap-2"
					role="radiogroup"
					aria-labelledby={`${id}-schedule`}
					aria-describedby={errors.scheduleType ? `${id}-schedule-error` : undefined}
				>
					{SCHEDULE_OPTIONS.map(({ value, description, Icon }) => {
						const selected = values.scheduleType === value;
						return (
							<label
								key={value}
								className={`flex items-start gap-2 rounded-md border min-h-12 px-3 py-2 cursor-pointer transition-colors ${
									selected ? "border-accent/60 bg-accent/10" : "border-input hover:bg-secondary/40"
								}`}
							>
								<input
									type="radio"
									name={`${id}-schedule-type`}
									value={value}
									checked={selected}
									onChange={() => set("scheduleType", value)}
									autoFocus={autoFocusField === "scheduleType" && selected}
									className="mt-1 shrink-0"
								/>
								<div className="flex-1 min-w-0">
									<div className="flex items-center gap-1.5 text-sm font-medium text-foreground">
										<Icon className="w-3.5 h-3.5" aria-hidden="true" />
										{SCHEDULE_TYPE_LABELS[value]}
									</div>
									<p className="text-[11px] text-muted-foreground mt-0.5">{description}</p>
								</div>
							</label>
						);
					})}
				</div>
				{errors.scheduleType && (
					<p id={`${id}-schedule-error`} className={errorCls}>
						{errors.scheduleType}
					</p>
				)}
			</fieldset>

			{timeBased && (
				<div className="grid grid-cols-2 gap-3">
					<div>
						<label htmlFor={`${id}-full-time-hours`} className={labelCls}>
							Full-time week (hours)
						</label>
						<input
							id={`${id}-full-time-hours`}
							type="number"
							min="0.5"
							step="0.5"
							inputMode="decimal"
							value={values.fullTimeHours}
							onChange={(e) => set("fullTimeHours", e.target.value)}
							autoFocus={autoFocusField === "fullTimeHours"}
							placeholder="e.g. 42"
							aria-invalid={errors.fullTimeHours ? true : undefined}
							aria-describedby={errors.fullTimeHours ? `${id}-full-time-hours-error` : undefined}
							className={inputCls}
						/>
						{errors.fullTimeHours && (
							<p id={`${id}-full-time-hours-error`} className={errorCls}>
								{errors.fullTimeHours}
							</p>
						)}
					</div>
					{values.scheduleType === "part_time" && (
						<div>
							<label htmlFor={`${id}-percentage`} className={labelCls}>
								Percentage
							</label>
							<div className="relative">
								<input
									id={`${id}-percentage`}
									type="number"
									min="1"
									max="99"
									step="0.5"
									inputMode="decimal"
									value={values.percentage}
									onChange={(e) => set("percentage", e.target.value)}
									autoFocus={autoFocusField === "percentage"}
									placeholder="e.g. 80"
									aria-invalid={errors.percentage ? true : undefined}
									aria-describedby={errors.percentage ? `${id}-percentage-error` : undefined}
									className={`${inputCls} pr-8`}
								/>
								<span
									className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground"
									aria-hidden="true"
								>
									%
								</span>
							</div>
							{errors.percentage && (
								<p id={`${id}-percentage-error`} className={errorCls}>
									{errors.percentage}
								</p>
							)}
						</div>
					)}
				</div>
			)}

			{values.scheduleType === "custom" && (
				<div>
					<label htmlFor={`${id}-weekly-hours`} className={labelCls}>
						Hours per week
					</label>
					<input
						id={`${id}-weekly-hours`}
						type="number"
						min="0"
						step="0.5"
						inputMode="decimal"
						value={values.weeklyHours}
						onChange={(e) => set("weeklyHours", e.target.value)}
						autoFocus={autoFocusField === "weeklyHours"}
						placeholder="e.g. 32"
						aria-invalid={errors.weeklyHours ? true : undefined}
						aria-describedby={errors.weeklyHours ? `${id}-weekly-hours-error` : undefined}
						className={inputCls}
					/>
					{errors.weeklyHours && (
						<p id={`${id}-weekly-hours-error`} className={errorCls}>
							{errors.weeklyHours}
						</p>
					)}
				</div>
			)}

			{preview && (
				<p className="text-xs text-muted-foreground tabular-nums" aria-live="polite">
					{preview}
				</p>
			)}

			<div>
				<label htmlFor={`${id}-effective-from`} className={labelCls}>
					{dateLabel}
				</label>
				<input
					id={`${id}-effective-from`}
					type="date"
					value={values.effectiveFrom}
					onChange={(e) => set("effectiveFrom", e.target.value)}
					autoFocus={autoFocusField === "effectiveFrom"}
					required
					aria-invalid={errors.effectiveFrom ? true : undefined}
					aria-describedby={errors.effectiveFrom ? `${id}-effective-from-error` : undefined}
					className={inputCls}
				/>
				{errors.effectiveFrom && (
					<p id={`${id}-effective-from-error`} className={errorCls}>
						{errors.effectiveFrom}
					</p>
				)}
			</div>

			{withNote && (
				<div>
					<label htmlFor={`${id}-note`} className={labelCls}>
						Note (optional)
					</label>
					<input
						id={`${id}-note`}
						value={values.note}
						onChange={(e) => set("note", e.target.value)}
						placeholder="e.g. Went to 80% after parental leave"
						className={inputCls}
					/>
				</div>
			)}
		</div>
	);
}
