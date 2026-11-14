import { describe, expect, it } from "vitest";
import { requestState } from "./Compliance";

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

describe("requestState", () => {
	it("counts the day of the month from the mail, to the deadline", () => {
		expect(requestState(row({}), "2026-11-01")).toBe("Open, day 1 of 31");
		expect(requestState(row({}), "2026-11-14")).toBe("Open, day 14 of 31");
		expect(requestState(row({ received_on: "2027-01-31" }), "2027-02-28")).toBe(
			"Open, day 29 of 29",
		);
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
