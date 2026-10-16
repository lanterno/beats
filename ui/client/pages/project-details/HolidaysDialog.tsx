/**
 * HolidaysDialog — where a day job's holidays differ from its region's
 * (docs/work-contracts.md, Decision 12), one year at a time: the region's
 * public holidays with a "Day off at work" tick each, the employer's own
 * company days with a name, and any date the contract still marks as not
 * given that is no longer a holiday of its region.
 *
 * Saving PUTs the whole contract with both lists; entries in other years go
 * out untouched. A weekend holiday costs nothing either way, so it has no
 * tick — unless the contract already stores it as not given (through the
 * API, say), when the tick stays so the date can be taken back. A date left over from a region change — or kept with no region at
 * all — is listed so it can be seen and removed: on its own it does nothing,
 * but a later region with a holiday that day would quietly make it a working
 * day. While a save is in flight the dialog stays open, as the booking
 * dialog does.
 */

import { ChevronLeft, ChevronRight, Plus, Trash2 } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import type { Contract, Project } from "@/entities/project";
import {
	toApiContract,
	useHolidayRegions,
	useProjectHolidays,
	useUpdateContract,
} from "@/entities/project";
import { apiFieldErrors, describeError } from "@/shared/api";
import { cn, parseIsoDate } from "@/shared/lib";
import { Button, Dialog } from "@/shared/ui";
import { isWeekdayIso, shortDate } from "./dates";
import { LABEL, NAV_BUTTON } from "./styles";

export interface HolidaysDialogProps {
	project: Pick<Project, "id"> & { contract: Contract };
	todayIso: string;
	onClose: () => void;
}

/** One company day as its inputs hold it. `year` is the page it was listed on. */
interface CompanyRow {
	key: number;
	year: number;
	date: string;
	name: string;
}

/** `notGiven` marks a date refused for being on the days not given, which the row offers to clear. */
type RowErrors = Partial<Record<"date" | "name", string>> & { notGiven?: true };

const FIELD =
	"w-full min-w-0 bg-secondary border-0 rounded-xl text-foreground px-3 py-2 text-[13px] font-medium focus:outline-hidden focus:ring-[3px] focus:ring-accent";
const ROW = "border-t border-border py-2 text-[12.5px]";
const REMOVE =
	"grid place-items-center w-7 h-7 shrink-0 rounded-full text-muted-foreground hover:bg-sidebar-accent hover:text-destructive transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40";

function yearOf(iso: string, fallback: number): number {
	return parseIsoDate(iso) ? Number(iso.slice(0, 4)) : fallback;
}

/** Each row's blocking problems: a missing name or date, a date twice, a date marked not given. */
function validate(rows: CompanyRow[], notGiven: Set<string>): Map<number, RowErrors> {
	const errors = new Map<number, RowErrors>();
	const seen = new Map<string, number>();
	for (const row of rows) {
		const own: RowErrors = {};
		if (!row.name.trim()) own.name = "Name the day";
		if (!parseIsoDate(row.date)) {
			own.date = "Enter a date";
		} else if (seen.has(row.date)) {
			own.date = "Another company holiday is on this day";
		} else if (notGiven.has(row.date)) {
			// The mark may sit on no row this page draws (a date the region has
			// no holiday on, or a year that failed to load), so the row clears it.
			own.date = "This day is marked as a holiday not given";
			own.notGiven = true;
		}
		if (parseIsoDate(row.date)) seen.set(row.date, row.key);
		if (own.date || own.name) errors.set(row.key, own);
	}
	return errors;
}

export function HolidaysDialog({ project, todayIso, onClose }: HolidaysDialogProps) {
	const id = useId();
	const contract = project.contract;
	const [year, setYear] = useState(Number(todayIso.slice(0, 4)));
	const [notGiven, setNotGiven] = useState(() => new Set(contract.holidaysNotGiven));
	// What the contract stored on opening: a weekend row keeps its tick while
	// it is being taken back, rather than vanishing on the first click.
	const [storedNotGiven] = useState(() => new Set(contract.holidaysNotGiven));
	const [rows, setRows] = useState<CompanyRow[]>(() =>
		contract.companyHolidays.map((h, i) => ({
			key: i,
			year: yearOf(h.date, year),
			date: h.date,
			name: h.name,
		})),
	);
	const [nextKey, setNextKey] = useState(contract.companyHolidays.length);
	const [errors, setErrors] = useState<Map<number, RowErrors>>(new Map());
	const [general, setGeneral] = useState<string[]>([]);
	const [saving, setSaving] = useState(false);

	const updateContract = useUpdateContract();
	const { data: regions } = useHolidayRegions();
	const {
		data: calendar,
		isLoading,
		error: calendarError,
	} = useProjectHolidays(project.id, year, {
		includeNotGiven: true,
	});

	const country = regions?.find((r) => r.code === contract.holidayCountry);
	const regionName = contract.holidaySubdivision
		? (country?.subdivisions.find((s) => s.code === contract.holidaySubdivision)?.name ??
			contract.holidaySubdivision)
		: (country?.name ?? contract.holidayCountry);

	const region = (calendar ?? []).filter((h) => h.source === "region");
	const regionDates = new Set(region.map((h) => h.date));
	const givenRegionDates = new Set(region.filter((h) => h.given).map((h) => h.date));
	// Only a loaded year can say a date is not the region's: until then, or
	// when the read fails, every date not given would look left over.
	const leftovers = calendar
		? [...notGiven].filter((d) => d.startsWith(`${year}-`) && !regionDates.has(d)).sort()
		: [];
	const shown = rows.filter((r) => r.year === year);

	const clearErrors = (key: number) =>
		setErrors((all) => {
			if (!all.has(key)) return all;
			const next = new Map(all);
			next.delete(key);
			return next;
		});

	const setRow = (key: number, patch: Partial<CompanyRow>) => {
		setRows((all) => all.map((r) => (r.key === key ? { ...r, ...patch } : r)));
		clearErrors(key);
	};

	const toggleGiven = (date: string, given: boolean) =>
		setNotGiven((all) => {
			const next = new Set(all);
			if (given) next.delete(date);
			else next.add(date);
			return next;
		});

	const addRow = () => {
		setRows((all) => [...all, { key: nextKey, year, date: "", name: "" }]);
		setNextKey((k) => k + 1);
	};

	const save = () => {
		const found = validate(rows, notGiven);
		setErrors(found);
		setGeneral([]);
		if (found.size > 0) {
			// A problem on another year's page would otherwise go unseen.
			const first = rows.find((r) => found.has(r.key));
			if (first && first.year !== year) setYear(first.year);
			return;
		}
		const sent = [...rows];
		const next: Contract = {
			...contract,
			companyHolidays: sent.map((r) => ({ date: r.date, name: r.name.trim() })),
			holidaysNotGiven: [...notGiven].sort(),
		};
		setSaving(true);
		updateContract.mutate(
			{ projectId: project.id, contract: toApiContract(next) },
			{
				onSuccess: () => {
					toast.success("Holidays saved");
					onClose();
				},
				onError: (err) => {
					// PUT /contract's body is the contract, so a row's path is
					// `company_holidays.N.name`, N its place in what was sent.
					const pinned = new Map<number, RowErrors>();
					const messages: string[] = [];
					for (const [path, message] of Object.entries(apiFieldErrors(err))) {
						const [list, index, leaf] = path.split(".");
						const row = list === "company_holidays" ? sent[Number(index)] : undefined;
						if (row && (leaf === "name" || leaf === "date")) {
							pinned.set(row.key, { ...pinned.get(row.key), [leaf]: message });
						} else {
							messages.push(message);
						}
					}
					if (pinned.size === 0 && messages.length === 0) {
						messages.push(describeError(err, "Failed to save the holidays"));
					}
					setErrors(pinned);
					setGeneral(messages);
				},
				onSettled: () => setSaving(false),
			},
		);
	};

	// Closed under a save, the write went on regardless.
	const close = () => {
		if (!saving) onClose();
	};

	return (
		<Dialog
			open
			onClose={close}
			title="Holidays"
			description="Where your employer's days off differ from the region's. Whole days only."
			contentClassName="sm:w-full sm:max-w-[460px]"
		>
			<form
				onSubmit={(e) => {
					e.preventDefault();
					save();
				}}
				noValidate
			>
				<div className="flex items-center justify-center gap-3">
					<button
						type="button"
						onClick={() => setYear((y) => y - 1)}
						aria-label="Previous year"
						className={NAV_BUTTON}
					>
						<ChevronLeft className="w-3.5 h-3.5" aria-hidden="true" />
					</button>
					<span className="font-heading text-[15px] font-extrabold" aria-live="polite">
						{year}
					</span>
					<button
						type="button"
						onClick={() => setYear((y) => y + 1)}
						aria-label="Next year"
						className={NAV_BUTTON}
					>
						<ChevronRight className="w-3.5 h-3.5" aria-hidden="true" />
					</button>
				</div>

				<section aria-labelledby={`${id}-public`} className="mt-4">
					<h3 id={`${id}-public`} className={LABEL}>
						Public holidays{regionName ? ` · ${regionName}` : ""}
					</h3>
					{!contract.holidayCountry ? (
						<p className="mt-2 text-[12.5px] text-muted-foreground font-medium">
							No region set — only company holidays apply.
						</p>
					) : isLoading ? (
						<p className="mt-2 text-[12.5px] text-muted-foreground">Loading…</p>
					) : calendarError ? (
						<p className="mt-2 text-[12.5px] text-destructive-ink font-medium" role="alert">
							{describeError(calendarError, `Failed to load the holidays for ${year}`)}
						</p>
					) : region.length === 0 ? (
						<p className="mt-2 text-[12.5px] text-muted-foreground font-medium">None in {year}.</p>
					) : (
						<ul className="mt-1.5 flex flex-col">
							{region.map((h) => (
								<li
									key={h.date}
									className={cn(ROW, "grid grid-cols-[minmax(0,1fr)_auto] gap-2 items-center")}
								>
									<span className="min-w-0">
										<b className="font-extrabold">{shortDate(h.date)}</b>
										<small className="block text-muted-foreground text-[11.5px] font-medium">
											{h.name}
										</small>
									</span>
									{isWeekdayIso(h.date) || storedNotGiven.has(h.date) ? (
										<label className="flex items-center gap-1.5 text-[12px] font-medium whitespace-nowrap">
											<input
												type="checkbox"
												checked={!notGiven.has(h.date)}
												onChange={(e) => toggleGiven(h.date, e.target.checked)}
												aria-label={`${h.name}, ${shortDate(h.date)}: day off at work`}
												className="accent-[hsl(var(--accent))]"
											/>
											Day off at work
										</label>
									) : (
										<span className="text-[11.5px] text-muted-foreground font-medium">
											on a weekend — costs nothing
										</span>
									)}
								</li>
							))}
						</ul>
					)}
				</section>

				<section aria-labelledby={`${id}-company`} className="mt-4">
					<h3 id={`${id}-company`} className={LABEL}>
						Company holidays
					</h3>
					{shown.length === 0 && (
						<p className="mt-2 text-[12.5px] text-muted-foreground font-medium">None in {year}.</p>
					)}
					<ul className="mt-1.5 flex flex-col">
						{shown.map((row, i) => {
							const own = errors.get(row.key) ?? {};
							const already =
								!own.date && givenRegionDates.has(row.date)
									? "Already a public holiday — changes nothing"
									: null;
							const errorId = `${id}-row-${row.key}-error`;
							return (
								<li key={row.key} className={ROW}>
									<div className="flex items-start gap-2">
										<input
											type="date"
											value={row.date}
											onChange={(e) => setRow(row.key, { date: e.target.value })}
											aria-label={`Company holiday ${i + 1}: date`}
											aria-invalid={own.date ? true : undefined}
											aria-describedby={own.date || own.name || already ? errorId : undefined}
											className={cn(FIELD, "font-mono font-bold w-[9.5rem] flex-none")}
										/>
										<input
											type="text"
											value={row.name}
											maxLength={80}
											onChange={(e) => setRow(row.key, { name: e.target.value })}
											placeholder="e.g. Christmas Eve"
											aria-label={`Company holiday ${i + 1}: name`}
											aria-invalid={own.name ? true : undefined}
											aria-describedby={own.date || own.name || already ? errorId : undefined}
											className={FIELD}
										/>
										<button
											type="button"
											onClick={() => setRows((all) => all.filter((r) => r.key !== row.key))}
											disabled={saving}
											aria-label={`Remove company holiday ${i + 1}`}
											className={REMOVE}
										>
											<Trash2 className="w-[13px] h-[13px]" aria-hidden="true" />
										</button>
									</div>
									{(own.date || own.name || already) && (
										<p
											id={errorId}
											className={cn(
												"mt-1 text-xs",
												own.date || own.name ? "text-destructive-ink" : "text-muted-foreground",
											)}
										>
											{[own.date, own.name, already].filter(Boolean).join(" · ")}
										</p>
									)}
									{own.notGiven && (
										<button
											type="button"
											onClick={() => {
												toggleGiven(row.date, true);
												clearErrors(row.key);
											}}
											disabled={saving}
											aria-label={`Clear the mark on ${shortDate(row.date)}`}
											className="mt-1 text-xs font-bold text-accent-ink underline-offset-2 hover:underline focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
										>
											Clear the mark
										</button>
									)}
								</li>
							);
						})}
					</ul>
					<Button type="button" variant="secondary" size="sm" onClick={addRow} className="mt-2">
						<Plus aria-hidden="true" />
						Add a day
					</Button>
				</section>

				{leftovers.length > 0 && (
					<section aria-labelledby={`${id}-leftover`} className="mt-4">
						<h3 id={`${id}-leftover`} className={LABEL}>
							No longer a holiday here
						</h3>
						<ul className="mt-1.5 flex flex-col">
							{leftovers.map((date) => (
								<li
									key={date}
									className={cn(ROW, "grid grid-cols-[minmax(0,1fr)_auto] gap-2 items-center")}
								>
									<span className="font-medium">
										<b className="font-extrabold">{shortDate(date)}</b> ·{" "}
										{contract.holidayCountry ? `not a holiday in ${regionName}` : "no region set"}
									</span>
									<button
										type="button"
										onClick={() => toggleGiven(date, true)}
										disabled={saving}
										aria-label={`Remove ${shortDate(date)} from the days not given`}
										className={REMOVE}
									>
										<Trash2 className="w-[13px] h-[13px]" aria-hidden="true" />
									</button>
								</li>
							))}
						</ul>
					</section>
				)}

				{general.length > 0 && (
					<div className="mt-3 text-sm text-destructive-ink space-y-0.5" role="alert">
						{general.map((message) => (
							<p key={message}>{message}</p>
						))}
					</div>
				)}

				<div className="flex justify-end gap-2.5 mt-[18px]">
					<Button type="button" variant="secondary" size="sm" onClick={close} disabled={saving}>
						Cancel
					</Button>
					<Button type="submit" size="sm" disabled={saving}>
						{saving ? "Saving…" : "Save"}
					</Button>
				</div>
			</form>
		</Dialog>
	);
}
