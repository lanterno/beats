import { describe, expect, it } from "vitest";
import { describeImport } from "./importSummary";

describe("describeImport", () => {
	// The SPA ships on its own: an API from before the 1.1 backup answers with
	// projects and beats alone, and that must read as it always did.
	it("reads an older API's answer as one without time off or adjustments", () => {
		expect(describeImport({ imported: { projects: 2, beats: 40 } })).toEqual({
			message: "Imported 2 projects and 40 sessions",
			leftOut: null,
		});
	});

	it("names the time off and the adjustments only when there are some", () => {
		expect(
			describeImport({
				imported: { projects: 1, beats: 1, absences: 0, balance_adjustments: 0 },
				skipped: [],
			}).message,
		).toBe("Imported 1 project and 1 session");
		expect(
			describeImport({
				imported: { projects: 3, beats: 120, absences: 4, balance_adjustments: 1 },
				skipped: [],
			}).message,
		).toBe("Imported 3 projects, 120 sessions, time off on 4 days and 1 balance adjustment");
	});

	it("names clients, project billing and billable marks only when a backup brings some", () => {
		expect(
			describeImport({
				imported: {
					projects: 2,
					beats: 40,
					absences: 0,
					balance_adjustments: 0,
					clients: 2,
					project_billing: 3,
					billable_overrides: 1,
				},
				skipped: [],
			}).message,
		).toBe(
			"Imported 2 projects, 40 sessions, 2 clients, billing for 3 projects and 1 billable mark",
		);
		expect(
			describeImport({
				imported: {
					projects: 1,
					beats: 5,
					absences: 0,
					balance_adjustments: 0,
					clients: 0,
					project_billing: 0,
					billable_overrides: 0,
				},
				skipped: [],
			}).message,
		).toBe("Imported 1 project and 5 sessions");
		// An API older than the 1.2 backup sends no billing counts at all.
		expect(
			describeImport({
				imported: { projects: 1, beats: 5, absences: 2, balance_adjustments: 0 },
				skipped: [],
			}).message,
		).toBe("Imported 1 project, 5 sessions and time off on 2 days");
	});

	it("says what it left out, by kind, so a partial import does not read as complete", () => {
		const skip = (collection: "absences" | "balance_adjustments") => ({
			collection,
			project_id: "p1",
			date: "2026-03-03",
			code: "NOT_A_DAY_JOB",
			detail: "Only a day-job project has a contract",
		});
		expect(
			describeImport({
				imported: { projects: 1, beats: 0, absences: 1, balance_adjustments: 0 },
				skipped: [skip("absences"), skip("absences"), skip("balance_adjustments")],
			}).leftOut,
		).toBe(
			"Left out time off on 2 days and 1 balance adjustment that the project no longer takes.",
		);
		expect(
			describeImport({
				imported: { projects: 1, beats: 0, absences: 0, balance_adjustments: 0 },
				skipped: [skip("absences")],
			}).leftOut,
		).toBe("Left out time off on 1 day that the project no longer takes.");
	});
});
