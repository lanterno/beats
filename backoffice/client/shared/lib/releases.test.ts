import { describe, expect, it } from "vitest";
import {
	buildLabel,
	isBad,
	releasesHeadline,
	rerunAdvice,
	statusLabel,
	unanswered,
} from "./releases";

const A = "a".repeat(40);
const B = "b".repeat(40);
const report = (fields: Record<string, unknown>) => ({
	builds: [],
	api_commit: A,
	web_commit: A,
	web_subject: null,
	repository: "o/r",
	unavailable: [],
	...fields,
});

describe("releasesHeadline", () => {
	it("says when both halves are on one commit", () => {
		expect(releasesHeadline(report({}))).toBe(
			"The API was deployed at aaaaaaa, and the web app is on the same commit.",
		);
	});

	it("says a web app on another commit is normal, not a problem", () => {
		expect(releasesHeadline(report({ web_commit: B }))).toContain("that is normal");
	});

	it("says unknown for what no source gave", () => {
		expect(releasesHeadline(report({ api_commit: null, web_commit: null }))).toBe(
			"The API's commit is unknown; the web app's is unknown.",
		);
	});
});

describe("unanswered and status", () => {
	it("names the sources that did not answer, and nothing when all did", () => {
		expect(unanswered(report({}))).toBeNull();
		expect(unanswered(report({ unavailable: ["builds", "web"] }))).toBe(
			"No answer from Cloud Build, the web app's version.json. What is shown is the last answer, if there was one.",
		);
	});

	it("reads Cloud Build's states, and an unknown one as unknown", () => {
		expect(statusLabel("SUCCESS")).toBe("Built");
		expect(statusLabel("NEW_THING")).toBe("Unknown");
		const row = {
			sha: A,
			status: "TIMEOUT",
			subject: null,
			created_at: null,
			finished_at: null,
			log_url: null,
			live: false,
			held: false,
		};
		expect(isBad(row)).toBe(true);
	});
});

describe("a build the freeze held back", () => {
	const row = {
		sha: A,
		status: "FAILURE",
		subject: null,
		created_at: null,
		finished_at: null,
		log_url: null,
		live: false,
		held: true,
	};

	it("is held, not a bad release to revert", () => {
		expect(buildLabel(row)).toBe("Held by the freeze");
		expect(isBad(row)).toBe(false);
		expect(isBad({ ...row, held: false })).toBe(true);
	});

	it("is named for re-running during the freeze and after it", () => {
		const rerun = { sha: B, subject: "Fix the thing", created_at: null, log_url: null };
		expect(rerunAdvice(rerun, true)).toBe(
			"Once it lifts, re-run the build of bbbbbbb (Fix the thing): a held build does not deploy by itself.",
		);
		expect(rerunAdvice(rerun, false)).toContain("The freeze held back bbbbbbb (Fix the thing)");
	});

	it("says nothing once the freeze is off and nothing waits", () => {
		expect(rerunAdvice(null, false)).toBeNull();
		expect(rerunAdvice(null, true)).toContain("if there is one");
	});
});
