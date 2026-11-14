import { describe, expect, it } from "vitest";
import { inState, jobsHeadline } from "./Jobs";

const job = (state: string) => ({ state });

describe("inState", () => {
	it("keeps everything for all", () => {
		expect(inState([job("queued"), job("done")], "all")).toHaveLength(2);
	});

	it("keeps one state", () => {
		expect(inState([job("queued"), job("done"), job("queued")], "queued")).toHaveLength(2);
	});

	// A document written before a state existed, or by a hand in mongosh.
	it("drops a row whose state is missing or not a string", () => {
		expect(inState([{}, { state: 3 }, job("failed")], "failed")).toHaveLength(1);
	});
});

describe("jobsHeadline", () => {
	it("says so when there is nothing to do", () => {
		expect(jobsHeadline([])).toBe("Nothing is waiting, and nothing has failed.");
		expect(jobsHeadline([job("done"), job("cancelled")])).toBe(
			"Nothing is waiting, and nothing has failed.",
		);
	});

	it("counts one of each in the singular", () => {
		expect(jobsHeadline([job("failed"), job("queued")])).toBe(
			"One job has failed and needs you. One is waiting out a window.",
		);
	});

	it("counts more than one in the plural", () => {
		expect(jobsHeadline([job("failed"), job("failed"), job("queued"), job("queued")])).toBe(
			"2 jobs have failed and need you. 2 are waiting out a window.",
		);
	});

	it("leaves out the half that is empty", () => {
		expect(jobsHeadline([job("failed")])).toBe("One job has failed and needs you.");
		expect(jobsHeadline([job("queued"), job("queued")])).toBe("2 jobs are waiting out a window.");
	});

	// A running job is neither: it is not waiting, and it has not failed.
	it("counts a running job as neither", () => {
		expect(jobsHeadline([job("running")])).toBe("Nothing is waiting, and nothing has failed.");
	});
});
