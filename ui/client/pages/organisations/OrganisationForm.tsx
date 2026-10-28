/**
 * OrganisationForm — what an organisation is set up with: its name, a
 * logo, the day its week starts, the employer's holiday region and its
 * timezone. The "New organisation" dialog and the Settings section are
 * the same form, the one blank and the other prefilled.
 *
 * The host does the write (`onSave`); a refusal comes back here and lands
 * on the input it names — a 422's `fields` by path, a 400 for a region or
 * timezone the API does not know on that field — else under the form.
 */

import { useId, useState } from "react";
import type { Organisation, OrganisationInput, WeekStart } from "@/entities/organisation";
import { WEEK_START_LABELS } from "@/entities/organisation";
import { useHolidayRegions } from "@/entities/project";
import { ApiError, apiFieldErrors, describeError } from "@/shared/api";
import { browserTimeZone } from "@/shared/lib";
import { Button } from "@/shared/ui";
import { ERROR, FIELD, LABEL, LEAD } from "./styles";

/**
 * The browser's own IANA zone names, as suggestions under the timezone
 * field. Feature-tested — the compiler's lib predates `supportedValuesOf`
 * — and the server still checks what is typed (400 INVALID_TIMEZONE).
 */
const TIMEZONES: readonly string[] =
	"supportedValuesOf" in Intl
		? (Intl as unknown as { supportedValuesOf(key: "timeZone"): string[] }).supportedValuesOf(
				"timeZone",
			)
		: [];

export interface OrganisationFormProps {
	/** The organisation to edit; a new one without it. */
	initial?: Organisation;
	onSave: (input: OrganisationInput) => Promise<void>;
	onCancel?: () => void;
	submitLabel: string;
}

type Field =
	| "name"
	| "logoUrl"
	| "weekStart"
	| "holidayCountry"
	| "holidaySubdivision"
	| "timezone";

interface FormErrors extends Partial<Record<Field, string>> {
	general?: string;
}

/** The body's paths, onto the inputs. */
const PATHS: Record<string, Field> = {
	name: "name",
	logo_url: "logoUrl",
	week_start: "weekStart",
	holiday_country: "holidayCountry",
	holiday_subdivision: "holidaySubdivision",
	timezone: "timezone",
};

/** A refusal about one field, with no path to say which. */
const CODES: Record<string, Field> = {
	UNKNOWN_HOLIDAY_REGION: "holidayCountry",
	INVALID_TIMEZONE: "timezone",
};

function formErrors(err: unknown): FormErrors {
	const out: FormErrors = {};
	const fields = apiFieldErrors(err);
	for (const [path, message] of Object.entries(fields)) {
		const field = PATHS[path.split(".")[0] ?? ""];
		if (field && !out[field]) out[field] = message;
		else out.general = out.general ? `${out.general} ${message}` : message;
	}
	if (Object.keys(fields).length === 0) {
		const field = err instanceof ApiError && err.code ? CODES[err.code] : undefined;
		if (field) out[field] = err instanceof ApiError ? err.message : String(err);
		else out.general = describeError(err, "The organisation could not be saved.");
	}
	return out;
}

const WEEK_STARTS = Object.keys(WEEK_START_LABELS) as WeekStart[];

export function OrganisationForm({
	initial,
	onSave,
	onCancel,
	submitLabel,
}: OrganisationFormProps) {
	const id = useId();
	const [name, setName] = useState(initial?.name ?? "");
	const [logoUrl, setLogoUrl] = useState(initial?.logoUrl ?? "");
	const [weekStart, setWeekStart] = useState<WeekStart>(initial?.weekStart ?? "monday");
	const [holidayCountry, setHolidayCountry] = useState(initial?.holidayCountry ?? "");
	const [holidaySubdivision, setHolidaySubdivision] = useState(initial?.holidaySubdivision ?? "");
	const [timezone, setTimezone] = useState(initial?.timezone ?? browserTimeZone());
	const [errors, setErrors] = useState<FormErrors>({});
	const [busy, setBusy] = useState(false);
	// The same list the contract form picks from; until it arrives, the
	// stored code stays selectable so a re-render cannot blank it.
	const { data: regions } = useHolidayRegions();
	const countries =
		regions ??
		(holidayCountry ? [{ code: holidayCountry, name: holidayCountry, subdivisions: [] }] : []);
	const subdivisions = countries.find((c) => c.code === holidayCountry)?.subdivisions ?? [];

	const save = async () => {
		if (!name.trim()) {
			setErrors({ name: "An organisation needs a name." });
			return;
		}
		if (!timezone.trim()) {
			setErrors({ timezone: "Pick a timezone." });
			return;
		}
		setErrors({});
		setBusy(true);
		try {
			await onSave({
				name: name.trim(),
				logoUrl: logoUrl.trim() || undefined,
				weekStart,
				holidayCountry: holidayCountry.trim().toUpperCase() || undefined,
				holidaySubdivision: holidaySubdivision.trim().toUpperCase() || undefined,
				timezone: timezone.trim(),
			});
		} catch (err) {
			setErrors(formErrors(err));
		} finally {
			setBusy(false);
		}
	};

	const field = (
		key: Field,
		label: string,
		input: (props: {
			id: string;
			"aria-invalid": true | undefined;
			"aria-describedby": string | undefined;
			className: string;
		}) => React.ReactNode,
	) => {
		const error = errors[key];
		return (
			<div>
				<label htmlFor={`${id}-${key}`} className={LABEL}>
					{label}
				</label>
				{input({
					id: `${id}-${key}`,
					"aria-invalid": error ? true : undefined,
					"aria-describedby": error ? `${id}-${key}-error` : undefined,
					className: FIELD,
				})}
				{error && (
					<p id={`${id}-${key}-error`} className={ERROR}>
						{error}
					</p>
				)}
			</div>
		);
	};

	return (
		<form
			onSubmit={(e) => {
				e.preventDefault();
				void save();
			}}
			noValidate
			className="space-y-3"
		>
			{field("name", "Name", (props) => (
				<input
					{...props}
					type="text"
					value={name}
					onChange={(e) => setName(e.target.value)}
					maxLength={80}
					autoFocus={!initial}
				/>
			))}
			{field("logoUrl", "Logo URL", (props) => (
				<input
					{...props}
					type="url"
					value={logoUrl}
					onChange={(e) => setLogoUrl(e.target.value)}
					placeholder="Optional"
					maxLength={2000}
				/>
			))}
			<div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
				{field("weekStart", "Week starts on", (props) => (
					<select
						{...props}
						value={weekStart}
						onChange={(e) => setWeekStart(e.target.value as WeekStart)}
					>
						{WEEK_STARTS.map((day) => (
							<option key={day} value={day}>
								{WEEK_START_LABELS[day]}
							</option>
						))}
					</select>
				))}
				{field("timezone", "Timezone", (props) => (
					<>
						<input
							{...props}
							type="text"
							value={timezone}
							onChange={(e) => setTimezone(e.target.value)}
							placeholder="Europe/Berlin"
							list="organisation-timezones"
						/>
						<datalist id="organisation-timezones">
							{TIMEZONES.map((tz) => (
								<option key={tz} value={tz} />
							))}
						</datalist>
					</>
				))}
			</div>
			<div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
				{field("holidayCountry", "Holiday region", (props) => (
					<select
						{...props}
						value={holidayCountry}
						onChange={(e) => {
							setHolidayCountry(e.target.value);
							setHolidaySubdivision("");
						}}
					>
						<option value="">No region</option>
						{countries.map((c) => (
							<option key={c.code} value={c.code}>
								{c.name}
							</option>
						))}
					</select>
				))}
				{subdivisions.length > 0 &&
					field("holidaySubdivision", "Subdivision", (props) => (
						<select
							{...props}
							value={holidaySubdivision}
							onChange={(e) => setHolidaySubdivision(e.target.value)}
						>
							<option value="">Whole country</option>
							{subdivisions.map((sd) => (
								<option key={sd.code} value={sd.code}>
									{sd.name}
								</option>
							))}
						</select>
					))}
			</div>
			<p className={`${LEAD} -mt-1`}>
				The public holidays a contract under {name.trim() || "this organisation"} starts from; each
				contract can still name its own.
			</p>

			{errors.general && (
				<p role="alert" className="text-sm text-destructive-ink">
					{errors.general}
				</p>
			)}

			<div className="flex justify-end gap-2.5 pt-1">
				{onCancel && (
					<Button type="button" variant="secondary" size="sm" onClick={onCancel} disabled={busy}>
						Cancel
					</Button>
				)}
				<Button type="submit" size="sm" disabled={busy}>
					{busy ? "Saving…" : submitLabel}
				</Button>
			</div>
		</form>
	);
}
