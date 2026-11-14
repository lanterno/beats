import { describe, expect, it } from "vitest";
import { deadlineOf, requestState } from "./Compliance";

const row = (fields: Record<string, unknown>) => ({
	id: "r",
	reference: "mail-1",
	received_on: "2026-11-01",
	subject_id: null,
	status: "open" as const,
	closed_at: null,
	closed_reason: null,
	...fields,
});

describe("deadlineOf", () => {
	it("is thirty days after the mail, across a month end", () => {
		expect(deadlineOf("2026-11-01")).toBe("2026-12-01");
		expect(deadlineOf("2026-12-15")).toBe("2027-01-14");
	});
});

describe("requestState", () => {
	it("counts the day of the month from the mail", () => {
		expect(requestState(row({}), "2026-11-01")).toBe("Open, day 1 of 30");
		expect(requestState(row({}), "2026-11-14")).toBe("Open, day 14 of 30");
	});

	it("reads the queue's state and the close reason", () => {
		expect(requestState(row({ status: "erasure_queued" }), "2026-11-14")).toBe("Erasure queued");
		expect(requestState(row({ status: "erasure_ran" }), "2026-11-14")).toBe(
			"Erasure ran — close it",
		);
		expect(requestState(row({ status: "closed", closed_reason: "erased" }), "2026-11-14")).toBe(
			"Closed: erased",
		);
	});
});
