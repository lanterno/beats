import type { Schemas } from "@/shared/api";

type Counts = Schemas["ImportCounts"];
type BillingCounts = "clients" | "project_billing" | "billable_overrides" | "billing_budgets";

/**
 * What this page reads of `POST /api/export/import`'s answer. The SPA and
 * the API ship on their own: an API older than the 1.2 backup answers
 * without clients, project billing or billable marks, and one older than
 * 1.3 without billing budgets.
 */
export type ImportResult = Pick<Schemas["ImportResponse"], "skipped"> & {
	imported: Omit<Counts, BillingCounts> & Partial<Pick<Counts, BillingCounts>>;
};

export interface ImportSummary {
	/** What the import wrote. */
	message: string;
	/** What it left out, or null when it left nothing out. */
	leftOut: string | null;
}

function count(n: number, one: string, many: string): string {
	return `${n} ${n === 1 ? one : many}`;
}

function timeOff(n: number): string {
	return `time off on ${count(n, "day", "days")}`;
}

function listed(parts: string[]): string {
	if (parts.length < 2) return parts.join("");
	return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

/**
 * The toast after a backup import. Time off, adjustments, clients, project
 * billing and billable marks are named only when there are some, so a
 * backup without a day job or a client reads as it always did. A record
 * the import left out is one the project would not take now (time off on
 * a project that is no longer a day job, an adjustment outside the
 * contract), and the toast says so, rather than the import reading as
 * complete.
 */
export function describeImport({ imported, skipped }: ImportResult): ImportSummary {
	const parts = [
		count(imported.projects, "project", "projects"),
		count(imported.beats, "session", "sessions"),
	];
	if (imported.absences > 0) parts.push(timeOff(imported.absences));
	if (imported.balance_adjustments > 0)
		parts.push(count(imported.balance_adjustments, "balance adjustment", "balance adjustments"));
	const clients = imported.clients ?? 0;
	const billed = imported.project_billing ?? 0;
	const marks = imported.billable_overrides ?? 0;
	if (clients > 0) parts.push(count(clients, "client", "clients"));
	if (billed > 0) parts.push(`billing for ${count(billed, "project", "projects")}`);
	if (marks > 0) parts.push(count(marks, "billable mark", "billable marks"));

	const skippedAbsences = skipped.filter((s) => s.collection === "absences").length;
	const skippedAdjustments = skipped.length - skippedAbsences;
	const leftOut: string[] = [];
	if (skippedAbsences > 0) leftOut.push(timeOff(skippedAbsences));
	if (skippedAdjustments > 0)
		leftOut.push(count(skippedAdjustments, "balance adjustment", "balance adjustments"));

	return {
		message: `Imported ${listed(parts)}`,
		leftOut:
			leftOut.length > 0 ? `Left out ${listed(leftOut)} that the project no longer takes.` : null,
	};
}
