/**
 * RevivedNotGivenNotice — under the region picker while the form changes a
 * contract's region: the dates the contract marks as not given that the new
 * region has a holiday on and the stored one had none, each with the
 * holiday's name. Left as they are they make those holidays working days,
 * so the notice offers to clear the marks in the same save, and to keep
 * them again.
 *
 * The form holds Save until the notice reports the check made
 * (`onChecked`): a save before both calendars are in would bring the marks
 * into force unseen. When a calendar fails to load the notice says the
 * marks could not be checked and offers to try again, and Save is let go:
 * held, an API without the route would block every region change.
 *
 * Mounted only on a region change of a contract with marks, so the form
 * reads no calendar otherwise.
 */

import { useEffect } from "react";
import { formatDateOnly } from "@/shared/lib";
import { Button } from "@/shared/ui";
import { useRegionCalendar } from "../api";
import type { Contract, RegionHoliday } from "../model";
import { notGivenYears, revivedNotGiven } from "../model";

type RegionChangeCheck =
	| { status: "pending" }
	| { status: "error"; retry: () => void }
	| { status: "done"; revived: RegionHoliday[] };

/**
 * A change from the contract's stored region to the form's, checked against
 * the contract's marks from both regions' calendars for the years the marks
 * fall in. No new region has no holiday to bring into force, and reads none.
 */
function useRegionChangeCheck(
	contract: Contract,
	country: string,
	subdivision: string,
): RegionChangeCheck {
	const years = country ? notGivenYears(contract) : [];
	const before = useRegionCalendar(
		contract.holidayCountry ?? "",
		contract.holidaySubdivision ?? "",
		years,
	);
	const after = useRegionCalendar(country, subdivision, years);
	if (before.status === "error" || after.status === "error") {
		return {
			status: "error",
			retry: () => {
				if (before.status === "error") before.retry();
				if (after.status === "error") after.retry();
			},
		};
	}
	if (before.status === "pending" || after.status === "pending") return { status: "pending" };
	return { status: "done", revived: revivedNotGiven(contract, before.holidays, after.holidays) };
}

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
	/**
	 * Whether the check is made, found or failed: false while a calendar
	 * loads, and again once the notice unmounts. Must be stable.
	 */
	onChecked: (checked: boolean) => void;
}

export function RevivedNotGivenNotice({
	contract,
	country,
	subdivision,
	regionName,
	cleared,
	onClear,
	onChecked,
}: RevivedNotGivenNoticeProps) {
	const check = useRegionChangeCheck(contract, country, subdivision);
	const checked = check.status !== "pending";
	useEffect(() => onChecked(checked), [checked, onChecked]);
	useEffect(() => () => onChecked(false), [onChecked]);
	const marks = contract.holidaysNotGiven.length;

	return (
		// Mounted while the region differs, so what the check finds is announced.
		<div aria-live="polite">
			{check.status === "pending" && (
				<p className="text-xs text-muted-foreground">
					{`Checking ${regionName}'s holidays against the ${marks === 1 ? "day" : "days"} this contract marks as not given…`}
				</p>
			)}
			{check.status === "error" && (
				<div className="rounded-2xl bg-secondary px-3 py-2 text-sm">
					<p className="text-destructive-ink">
						{marks === 1
							? `Could not check the day this contract marks as not given against ${regionName}'s holidays. Saved now, the mark stays, and if ${regionName} has a holiday that day it becomes a working day.`
							: `Could not check the ${marks} days this contract marks as not given against ${regionName}'s holidays. Saved now, the marks stay, and a holiday ${regionName} has on one of them becomes a working day.`}
					</p>
					<Button
						type="button"
						variant="link"
						size="sm"
						onClick={check.retry}
						className="px-0 h-auto mt-1 text-xs"
					>
						Try again
					</Button>
				</div>
			)}
			{check.status === "done" && check.revived.length > 0 && (
				<RevivedList
					revived={check.revived}
					regionName={regionName}
					cleared={cleared}
					onClear={onClear}
				/>
			)}
		</div>
	);
}

function RevivedList({
	revived,
	regionName,
	cleared,
	onClear,
}: { revived: RegionHoliday[] } & Pick<
	RevivedNotGivenNoticeProps,
	"regionName" | "cleared" | "onClear"
>) {
	const one = revived.length === 1;
	return (
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
	);
}
