/**
 * VacationFields — the contract section's vacation block in the project
 * form (docs/work-contracts.md, Decision 14): the days per year, what
 * becomes of unused days, and the dated opening counting starts from.
 * Optional: with the days per year empty there is no entitlement, and the
 * rest of the block hides.
 *
 * The carry-over uses the form's option-card radiogroup (the Kind and Goal
 * type idiom), and its number sits under the cards once "Up to" is chosen.
 * Nothing is prefilled: the opening is a figure off the contract or an HR
 * statement, and a guess here would be counted as fact.
 */

import type { CarryOver, ContractFrameErrors, ContractFrameValues } from "../model";

const CARRY_OVER_OPTIONS: { value: CarryOver; label: string; description: string }[] = [
	{ value: "all", label: "All carry over", description: "Every unused day moves to next year" },
	{ value: "capped", label: "Up to a limit", description: "Some days carry, the rest lapse" },
	{ value: "none", label: "Lapse at year end", description: "Unused days are gone on Dec 31" },
];

export interface VacationFieldsProps {
	values: ContractFrameValues;
	onChange: <K extends keyof ContractFrameValues>(k: K, v: ContractFrameValues[K]) => void;
	errors: ContractFrameErrors;
	inputCls: string;
	labelCls: string;
	errorCls: string;
}

const hintCls = "mt-1 text-[11px] text-muted-foreground/70";

export function VacationFields({
	values,
	onChange,
	errors,
	inputCls,
	labelCls,
	errorCls,
}: VacationFieldsProps) {
	const tracked = values.vacationDaysPerYear.trim() !== "";
	const describedBy = (field: keyof ContractFrameValues, id: string, hint?: string) =>
		errors[field] ? `${id}-error` : hint;

	return (
		<div className="space-y-3">
			<div>
				<label htmlFor="project-form-vacation-days" className={labelCls}>
					Vacation days per year (optional)
				</label>
				<input
					id="project-form-vacation-days"
					type="number"
					min="0"
					step="0.5"
					inputMode="decimal"
					value={values.vacationDaysPerYear}
					onChange={(e) => onChange("vacationDaysPerYear", e.target.value)}
					placeholder="e.g. 25"
					aria-invalid={errors.vacationDaysPerYear ? true : undefined}
					aria-describedby={describedBy(
						"vacationDaysPerYear",
						"project-form-vacation-days",
						"project-form-vacation-days-hint",
					)}
					className={inputCls}
				/>
				{errors.vacationDaysPerYear ? (
					<p id="project-form-vacation-days-error" className={errorCls}>
						{errors.vacationDaysPerYear}
					</p>
				) : (
					<p id="project-form-vacation-days-hint" className={hintCls}>
						For a five-day week: a 4-day week with 20 days is 5 weeks, enter 25.
					</p>
				)}
			</div>

			{tracked && (
				<>
					<fieldset>
						<legend id="project-form-vacation-carry-over" className={labelCls}>
							Unused days
						</legend>
						<div
							className="grid grid-cols-1 sm:grid-cols-3 gap-2"
							role="radiogroup"
							aria-labelledby="project-form-vacation-carry-over"
							aria-describedby={
								errors.vacationCarryOver ? "project-form-vacation-carry-over-error" : undefined
							}
						>
							{CARRY_OVER_OPTIONS.map(({ value, label, description }) => {
								const selected = values.vacationCarryOver === value;
								return (
									<label
										key={value}
										className={`flex items-start gap-2 rounded-2xl min-h-12 px-3 py-2 cursor-pointer transition-colors ${
											selected ? "bg-sidebar-accent" : "bg-secondary hover:bg-sidebar-accent/60"
										}`}
									>
										<input
											type="radio"
											name="project-form-vacation-carry-over"
											value={value}
											checked={selected}
											onChange={() => onChange("vacationCarryOver", value)}
											aria-invalid={errors.vacationCarryOver ? true : undefined}
											className="mt-1 shrink-0"
										/>
										<div className="flex-1 min-w-0">
											<div className="text-sm font-medium text-foreground">{label}</div>
											<p className="text-[11px] text-muted-foreground mt-0.5">{description}</p>
										</div>
									</label>
								);
							})}
						</div>
						{errors.vacationCarryOver && (
							<p id="project-form-vacation-carry-over-error" className={errorCls}>
								{errors.vacationCarryOver}
							</p>
						)}
					</fieldset>

					{values.vacationCarryOver === "capped" && (
						<div>
							<label htmlFor="project-form-vacation-carry-over-max" className={labelCls}>
								Days that carry over, at most
							</label>
							<input
								id="project-form-vacation-carry-over-max"
								type="number"
								min="0"
								step="0.5"
								inputMode="decimal"
								value={values.vacationCarryOverMax}
								onChange={(e) => onChange("vacationCarryOverMax", e.target.value)}
								aria-invalid={errors.vacationCarryOverMax ? true : undefined}
								aria-describedby={describedBy(
									"vacationCarryOverMax",
									"project-form-vacation-carry-over-max",
								)}
								className={inputCls}
							/>
							{errors.vacationCarryOverMax && (
								<p id="project-form-vacation-carry-over-max-error" className={errorCls}>
									{errors.vacationCarryOverMax}
								</p>
							)}
						</div>
					)}

					<div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
						<div>
							<label htmlFor="project-form-vacation-opening-on" className={labelCls}>
								Counting from
							</label>
							<input
								id="project-form-vacation-opening-on"
								type="date"
								value={values.vacationOpeningOn}
								onChange={(e) => onChange("vacationOpeningOn", e.target.value)}
								aria-invalid={errors.vacationOpeningOn ? true : undefined}
								aria-describedby={describedBy(
									"vacationOpeningOn",
									"project-form-vacation-opening-on",
									"project-form-vacation-opening-hint",
								)}
								className={inputCls}
							/>
							{errors.vacationOpeningOn && (
								<p id="project-form-vacation-opening-on-error" className={errorCls}>
									{errors.vacationOpeningOn}
								</p>
							)}
						</div>
						<div>
							<label htmlFor="project-form-vacation-opening-days" className={labelCls}>
								Days left that morning
							</label>
							<input
								id="project-form-vacation-opening-days"
								type="number"
								step="0.5"
								inputMode="decimal"
								value={values.vacationOpeningDays}
								onChange={(e) => onChange("vacationOpeningDays", e.target.value)}
								aria-invalid={errors.vacationOpeningDays ? true : undefined}
								aria-describedby={describedBy(
									"vacationOpeningDays",
									"project-form-vacation-opening-days",
									"project-form-vacation-opening-hint",
								)}
								className={inputCls}
							/>
							{errors.vacationOpeningDays && (
								<p id="project-form-vacation-opening-days-error" className={errorCls}>
									{errors.vacationOpeningDays}
								</p>
							)}
						</div>
					</div>
					<p id="project-form-vacation-opening-hint" className={hintCls}>
						From your contract or HR statement: the days left for the rest of that year, carry-over
						included. Leave taken before this date is not counted.
					</p>
				</>
			)}
		</div>
	);
}
