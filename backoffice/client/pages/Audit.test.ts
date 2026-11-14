import { describe, expect, it } from "vitest";
import { matching } from "./Audit";

const rows = [
	{ command: "account.suspend", subject_id: "6730f1a2b3c4d5e6f7a8b9c0" },
	{ command: "organisation.delete", subject_id: "6730aaa2b3c4d5e6f7a8b9c1" },
	{ command: "retention.purge", subject_id: "all" },
];

describe("matching", () => {
	it("keeps every row for an empty filter, or one of only spaces", () => {
		expect(matching(rows, "")).toHaveLength(3);
		expect(matching(rows, "   ")).toHaveLength(3);
	});

	it("finds an account by the id an operator has in hand", () => {
		expect(matching(rows, "6730f1a2b3c4d5e6f7a8b9c0")).toEqual([rows[0]]);
	});

	it("finds every row of one command", () => {
		expect(matching(rows, "organisation.")).toEqual([rows[1]]);
	});

	it("ignores case and the spaces around a pasted id", () => {
		expect(matching(rows, "  6730F1A2B3C4D5E6F7A8B9C0  ")).toEqual([rows[0]]);
	});

	it("answers nothing rather than everything when nothing matches", () => {
		expect(matching(rows, "u_nobody")).toEqual([]);
	});

	// The audit holds a subject's id and the command, and this filter reads
	// those two fields. A row whose operator or payload happens to contain
	// the text is not a match: the filter means "this subject", not "this
	// text somewhere in the record".
	it("looks at the subject and the command and nowhere else", () => {
		const row = { command: "account.suspend", subject_id: "abc", operator_email: "zed@x.test" };
		expect(matching([row], "zed")).toEqual([]);
	});
});
