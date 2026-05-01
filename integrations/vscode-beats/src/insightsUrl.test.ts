// Tests for buildInsightsUrl. Run with `npm test` — uses node --test
// against the compiled JS in out/, so we depend only on stdlib +
// typescript output, no test framework added to the extension.
//
// Cross-language parity: each assertion mirrors a case in the
// daemon's open_test.go (Go) so a deep link from `beatsd open` and
// from "Beats: Open Insights" lands at the same URL given the same
// inputs.

import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import { buildInsightsUrl } from "./insightsUrl";

describe("buildInsightsUrl", () => {
	it("returns the bare /insights URL when no filter is given", () => {
		assert.equal(buildInsightsUrl("http://localhost:8080"), "http://localhost:8080/insights");
		assert.equal(buildInsightsUrl("http://localhost:8080", {}), "http://localhost:8080/insights");
	});

	it("appends ?repo=<encoded path> when a workspace is open", () => {
		assert.equal(
			buildInsightsUrl("http://localhost:8080", { repo: "/Users/me/code/beats" }),
			"http://localhost:8080/insights?repo=%2FUsers%2Fme%2Fcode%2Fbeats",
		);
	});

	it("strips a trailing slash on the base URL so we don't double up", () => {
		// Self-hosted users sometimes set webUrl with a trailing slash.
		// Normalize so we never produce //insights.
		assert.equal(
			buildInsightsUrl("https://beats.example.com/"),
			"https://beats.example.com/insights",
		);
		assert.equal(
			buildInsightsUrl("https://beats.example.com/", { repo: "/code/x" }),
			"https://beats.example.com/insights?repo=%2Fcode%2Fx",
		);
	});

	it("treats null/empty repo as no workspace", () => {
		assert.equal(
			buildInsightsUrl("http://localhost:8080", { repo: null }),
			"http://localhost:8080/insights",
		);
		assert.equal(
			buildInsightsUrl("http://localhost:8080", { repo: "" }),
			"http://localhost:8080/insights",
		);
	});

	it("URL-encodes paths with spaces and special characters", () => {
		// Spaces happen on macOS user folders; & / = could appear in
		// pathological cases. The web's useUrlParam reads via
		// URLSearchParams.get() which decodes — verify the encoding
		// chain matches.
		const url = buildInsightsUrl("http://localhost:8080", {
			repo: "/Users/me/My Code/x&y=z",
		});
		const parsed = new URL(url);
		assert.equal(parsed.pathname, "/insights");
		assert.equal(parsed.searchParams.get("repo"), "/Users/me/My Code/x&y=z");
	});

	it("appends ?language=<id> when only language is set", () => {
		const url = buildInsightsUrl("http://localhost:8080", { language: "go" });
		assert.equal(new URL(url).searchParams.get("language"), "go");
	});

	it("appends ?bundle=<id> when only bundle is set", () => {
		const url = buildInsightsUrl("http://localhost:8080", {
			bundle: "com.microsoft.VSCode",
		});
		assert.equal(new URL(url).searchParams.get("bundle"), "com.microsoft.VSCode");
	});

	it("composes all three axes in the URL", () => {
		const url = buildInsightsUrl("http://localhost:8080", {
			repo: "/Users/me/code/beats",
			language: "go",
			bundle: "com.microsoft.VSCode",
		});
		const params = new URL(url).searchParams;
		assert.equal(params.get("repo"), "/Users/me/code/beats");
		assert.equal(params.get("language"), "go");
		assert.equal(params.get("bundle"), "com.microsoft.VSCode");
	});

	it("orders keys alphabetically — bundle, language, repo — for stable URLs", () => {
		// Same rule as the daemon's url.Values.Encode behavior. Two
		// consecutive runs produce byte-identical URLs (matters for
		// clipboard diffs and shell history grepping).
		const url = buildInsightsUrl("http://localhost:8080", {
			repo: "r",
			language: "l",
			bundle: "b",
		});
		assert.equal(url, "http://localhost:8080/insights?bundle=b&language=l&repo=r");
	});
});
