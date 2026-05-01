// Tests for buildInsightsUrl. Run with `npm test` — uses node --test
// against the compiled JS in out/, so we depend only on stdlib +
// typescript output, no test framework added to the extension.

import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import { buildInsightsUrl } from "./insightsUrl";

describe("buildInsightsUrl", () => {
	it("returns the bare /insights URL when no workspace is open", () => {
		assert.equal(
			buildInsightsUrl("http://localhost:8080", null),
			"http://localhost:8080/insights",
		);
	});

	it("appends ?repo=<encoded path> when a workspace is open", () => {
		assert.equal(
			buildInsightsUrl("http://localhost:8080", "/Users/me/code/beats"),
			"http://localhost:8080/insights?repo=%2FUsers%2Fme%2Fcode%2Fbeats",
		);
	});

	it("strips a trailing slash on the base URL so we don't double up", () => {
		// Self-hosted users sometimes set webUrl with a trailing slash.
		// Normalize so we never produce //insights.
		assert.equal(
			buildInsightsUrl("https://beats.example.com/", null),
			"https://beats.example.com/insights",
		);
		assert.equal(
			buildInsightsUrl("https://beats.example.com/", "/code/x"),
			"https://beats.example.com/insights?repo=%2Fcode%2Fx",
		);
	});

	it("treats empty string as no workspace", () => {
		assert.equal(
			buildInsightsUrl("http://localhost:8080", ""),
			"http://localhost:8080/insights",
		);
	});

	it("URL-encodes paths with spaces and special characters", () => {
		// Spaces happen on macOS user folders; & / = could appear in
		// pathological cases. The web's useUrlParam reads via
		// URLSearchParams.get() which decodes — verify the encoding
		// chain matches.
		const url = buildInsightsUrl("http://localhost:8080", "/Users/me/My Code/x&y=z");
		const parsed = new URL(url);
		assert.equal(parsed.pathname, "/insights");
		assert.equal(parsed.searchParams.get("repo"), "/Users/me/My Code/x&y=z");
	});
});
