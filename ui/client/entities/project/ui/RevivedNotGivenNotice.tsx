/**
 * RevivedNotGivenNotice — under the region picker while the form changes a
 * contract's region: the dates the contract marks as not given that the new
 * region has a holiday on and the stored one had none, each with the
 * holiday's name. Left as they are they make those holidays working days,
 * so the notice offers to clear the marks in the same save, and to keep
 * them again. Nothing is said until both regions' calendars are in, or when
 * one fails to load: the Holidays dialog still lists every mark.
 *
 * Mounted only on a region change of a contract with marks, so the form
 * reads no calendar otherwise.
 */

import { formatDateOnly } from "@/shared/lib";
import { Button } from "@/shared/ui";
import { useRegionCalendar } from "../api";
import type { Contract } from "../model";
import { notGivenYears, revivedNotGiven } from "../model";

export interface RevivedNotGivenNoticeProps {
	/** The contract as stored: its region, its marks and its company days. */
	contract: Contract;
	/** The region the form now holds; "" is none. */
	country: string;
	subdivision: string;
	/** How the new region reads in a sentence ("Zürich"). */
	regionName: string;
	/** Whether the save drops the marks listed. */
	cleared: boolean;
	/** The marks to drop on save: the dates listed, or none to keep them. */
	onClear: (dates: string[]) => void;
}

export function RevivedNotGivenNotice({
	contract,
	country,
	subdivision,
	regionName,
	cleared,
	onClear,
}: RevivedNotGivenNoticeProps) {
	const years = notGivenYears(contract);
	const before = useRegionCalendar(
		contract.holidayCountry ?? "",
		contract.holidaySubdivision ?? "",
		years,
	);
	const after = useRegionCalendar(country, subdivision, years);
	const revived = before && after ? revivedNotGiven(contract, before, after) : [];
	const one = revived.length === 1;

	return (
		// Always mounted while the region differs, so the dates are announced
		// when the calendars arrive.
		<div aria-live="polite">
			{revived.length > 0 && (
				<div className="rounded-2xl bg-secondary px-3 py-2 text-sm">
					<p className={cleared ? "text-foreground" : "text-destructive-ink"}>
						{cleared
							? `The ${one ? "mark is" : "marks are"} cleared on save, so ${one ? "this day is a holiday" : "these days are holidays"}:`
							: `This contract marks ${one ? "a day" : `${revived.length} days`} as not given that ${regionName} has a holiday on, so ${one ? "it would be a working day" : "they would be working days"}:`}
					</p>
					<ul className="mt-1 text-foreground">
						{revived.map((holiday) => (
							<li key={holiday.date}>
								<b className="font-bold">{formatDateOnly(holiday.date)}</b> · {holiday.name}
							</li>
						))}
					</ul>
					<Button
						type="button"
						variant="link"
						size="sm"
						onClick={() => onClear(cleared ? [] : revived.map((holiday) => holiday.date))}
						className="px-0 h-auto mt-1 text-xs"
					>
						{cleared ? `Keep the ${one ? "mark" : "marks"}` : `Clear the ${one ? "mark" : "marks"}`}
					</Button>
				</div>
			)}
		</div>
	);
}
