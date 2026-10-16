import type { Schemas } from "@/shared/api";

type Counts = Schemas["ImportCounts"];

/**
 * `POST /api/export/import`'s answer, as this page may receive it. The SPA
 * and the API ship on their own, and an API older than the 1.1 backup
 * answers with `projects` and `beats` alone: no time off, no adjustments,
 * and nothing `skipped`.
 */
export type ImportResult = {
	imported: Pick<Counts, "projects" | "beats"> &
		Partial<Pick<Counts, "absences" | "balance_adjustments">>;
	skipped?: Schemas["ImportSkip"][];
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
 * The toast after a backup import. Time off and adjustments are named only
 * when there are some, so a backup without a day job reads as it always
 * did. A record the import left out is one the project would not take now
 * (time off on a project that is no longer a day job, an adjustment outside
 * the contract), and the toast says so, rather than the import reading as
 * complete.
 */
export function describeImport({ imported, skipped = [] }: ImportResult): ImportSummary {
	const parts = [
		count(imported.projects, "project", "projects"),
		count(imported.beats, "session", "sessions"),
	];
	const absences = imported.absences ?? 0;
	const adjustments = imported.balance_adjustments ?? 0;
	if (absences > 0) parts.push(timeOff(absences));
	if (adjustments > 0) parts.push(count(adjustments, "balance adjustment", "balance adjustments"));

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
