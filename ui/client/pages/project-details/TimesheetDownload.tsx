/**
 * TimesheetDownload — the Contract panel's "Timesheet" block
 * (docs/project-page.md, "How the page is put together"): pick a month,
 * download its CSV for the employer. Only the months `timesheetMonths`
 * offers are listed, newest first — the ones the API has a sheet for — and
 * a month cut short says where it stops. The figures are in the file and
 * nowhere on the page: the page reads one ledger, and does not rebuild a
 * month in the browser. Nothing renders while there is no month to offer.
 */

import { Download, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import type { Contract, ProjectWithDuration } from "@/entities/project";
import {
	downloadTimesheet,
	timesheetFilename,
	timesheetMonthLabel,
	timesheetMonths,
} from "@/entities/project";
import { describeError } from "@/shared/api";
import { Button } from "@/shared/ui";
import { LABEL, SELECT_PILL } from "./styles";

export function TimesheetDownload({
	project,
	contract,
	todayIso,
}: {
	project: ProjectWithDuration;
	contract: Contract;
	todayIso: string;
}) {
	const [chosen, setChosen] = useState<string | null>(null);
	const [downloading, setDownloading] = useState(false);
	const months = timesheetMonths(contract, todayIso);
	if (months.length === 0) return null;
	// A month that is no longer offered (the contract changed) falls back to the newest.
	const sheet = months.find((m) => m.month === chosen) ?? months[0];

	const handleDownload = async () => {
		const filename = timesheetFilename(project.name, sheet);
		setDownloading(true);
		try {
			await downloadTimesheet(project.id, sheet.month, filename);
			toast.success(`Downloaded ${filename}`);
		} catch (err) {
			toast.error(describeError(err, "Download failed"));
		} finally {
			setDownloading(false);
		}
	};

	return (
		<div className="mt-4">
			<h4 className={LABEL}>Timesheet</h4>
			<div className="mt-2 flex flex-wrap items-center gap-2">
				<select
					aria-label="Timesheet month"
					value={sheet.month}
					onChange={(e) => setChosen(e.target.value)}
					disabled={downloading}
					className={SELECT_PILL}
				>
					{months.map((m) => (
						<option key={m.month} value={m.month}>
							{timesheetMonthLabel(m)}
						</option>
					))}
				</select>
				<Button
					type="button"
					variant="secondary"
					size="sm"
					onClick={handleDownload}
					disabled={downloading}
				>
					{downloading ? (
						<Loader2 className="animate-spin" aria-hidden="true" />
					) : (
						<Download aria-hidden="true" />
					)}
					Download CSV
				</Button>
			</div>
		</div>
	);
}
