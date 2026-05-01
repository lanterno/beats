// Tests for formatStatusBar / formatUptime. Pure helpers — no vscode
// import — so they run under `node --test` like insightsUrl.test.ts.

import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import {
	formatStatusBar,
	formatUptime,
	isStaleNoEmissions,
	shortRepoTail,
} from "./statusBar";

describe("formatStatusBar", () => {
	it("offline: shows the slash icon when health is null", () => {
		const { text, tooltip } = formatStatusBar(null);
		assert.match(text, /\$\(circle-slash\)/);
		assert.match(text, /Beats/);
		assert.match(tooltip, /offline/i);
		assert.match(tooltip, /beatsd run/);
	});

	it("offline: shows the slash icon when ok=false", () => {
		// Defensive — the daemon would never set ok=false today, but a
		// future version might add a degraded state. The status bar
		// should still treat that as "not capturing".
		const { text } = formatStatusBar({
			ok: false,
			version: "1.0.0",
			uptimeSec: 3600,
			editorCount: 1, windowsEmitted: 0, windowsDropped: 0,
		});
		assert.match(text, /\$\(circle-slash\)/);
	});

	it("connected: shows the zap icon and the daemon version in the tooltip", () => {
		const { text, tooltip } = formatStatusBar({
			ok: true,
			version: "v1.2.3",
			uptimeSec: 3600,
			editorCount: 1, windowsEmitted: 0, windowsDropped: 0,
		});
		assert.match(text, /\$\(zap\)/);
		assert.match(tooltip, /connected/i);
		assert.match(tooltip, /v1\.2\.3/);
	});

	it("connected: pluralizes 'editor' for editor_count != 1", () => {
		// English grammar matters in tooltips — "1 editors sending" reads
		// off. Cover both branches.
		const single = formatStatusBar({
			ok: true,
			version: "dev",
			uptimeSec: 60,
			editorCount: 1, windowsEmitted: 0, windowsDropped: 0,
		});
		assert.match(single.tooltip, /1 editor /);

		const multiple = formatStatusBar({
			ok: true,
			version: "dev",
			uptimeSec: 60,
			editorCount: 2, windowsEmitted: 0, windowsDropped: 0,
		});
		assert.match(multiple.tooltip, /2 editors/);
	});

	it("connected: falls back to 'dev' when version is empty", () => {
		// editor.New("") is allowed when the binary doesn't carry a
		// version stamp (dev builds). The tooltip should still read
		// cleanly — no "(...)" with nothing inside.
		const { tooltip } = formatStatusBar({
			ok: true,
			version: "",
			uptimeSec: 60,
			editorCount: 0, windowsEmitted: 0, windowsDropped: 0,
		});
		assert.match(tooltip, /\(dev\)/);
	});

	it("connected with summary: shows the avg score in the status text", () => {
		const { text, tooltip } = formatStatusBar(
			{ ok: true, version: "v1.0.0", uptimeSec: 60, editorCount: 1, windowsEmitted: 0, windowsDropped: 0 },
			{ count: 23, avg: 0.67, peak: 0.91 },
		);
		// Bare "Beats 67" so it stays compact in the status bar.
		assert.match(text, /\$\(zap\) Beats 67/);
		// Tooltip carries the full triple — avg + peak + count.
		assert.match(tooltip, /avg 67\/100/);
		assert.match(tooltip, /peak 91\/100/);
		assert.match(tooltip, /23 windows/);
	});

	it("connected with empty summary: omits the score and falls back to plain 'Beats'", () => {
		// Early in the morning before any flow has accrued — count=0
		// shouldn't render "Beats 0" (reads as "you're at zero",
		// false signal). Plain "Beats" matches the no-summary case.
		const { text, tooltip } = formatStatusBar(
			{ ok: true, version: "v1.0.0", uptimeSec: 60, editorCount: 1, windowsEmitted: 0, windowsDropped: 0 },
			{ count: 0, avg: 0, peak: 0 },
		);
		assert.equal(text, "$(zap) Beats");
		assert.doesNotMatch(tooltip, /Today/);
	});

	it("connected with windows_emitted > 0: surfaces the count in the daemon line", () => {
		const { tooltip } = formatStatusBar({
			ok: true,
			version: "v1.0.0",
			uptimeSec: 3600,
			editorCount: 1,
			windowsEmitted: 142,
			windowsDropped: 0,
		});
		assert.match(tooltip, /142 emitted/);
	});

	it("connected with windows_emitted = 0: omits the chunk cleanly", () => {
		// Avoid "0 emitted" in the tooltip — fresh daemon with no
		// windows yet shouldn't read like a degraded state.
		const { tooltip } = formatStatusBar({
			ok: true,
			version: "v1.0.0",
			uptimeSec: 60,
			editorCount: 1,
			windowsEmitted: 0,
			windowsDropped: 0,
		});
		assert.doesNotMatch(tooltip, /emitted/);
	});

	it("connected with topRepo/topLanguage: surfaces them in the tooltip", () => {
		const { tooltip } = formatStatusBar(
			{ ok: true, version: "v1.0.0", uptimeSec: 60, editorCount: 1, windowsEmitted: 0, windowsDropped: 0 },
			{
				count: 23,
				avg: 0.67,
				peak: 0.91,
				topRepo: "/Users/me/code/beats",
				topLanguage: "go",
			},
		);
		assert.match(tooltip, /best on code\/beats/);
		assert.match(tooltip, /in go/);
	});

	it("connected without top_* axes: omits the best-on line cleanly", () => {
		// The /summary response sets top_repo/top_language to null when
		// no editor heartbeats covered the slice. The tooltip should
		// skip that line rather than render "best on  · in".
		const { tooltip } = formatStatusBar(
			{ ok: true, version: "v1.0.0", uptimeSec: 60, editorCount: 1, windowsEmitted: 0, windowsDropped: 0 },
			{ count: 23, avg: 0.67, peak: 0.91 },
		);
		assert.doesNotMatch(tooltip, /best on/);
	});

	it("connected with no summary fetched: same as plain 'Beats'", () => {
		// Distinct from "summary fetched but empty" — this is the path
		// where the daemon returned 503 (no fetcher) or 502 (upstream
		// failed). The status text and the no-summary case should be
		// identical so a transient API blip doesn't reshape the bar.
		const noFetch = formatStatusBar(
			{ ok: true, version: "v1.0.0", uptimeSec: 60, editorCount: 1, windowsEmitted: 0, windowsDropped: 0 },
			null,
		);
		const empty = formatStatusBar(
			{ ok: true, version: "v1.0.0", uptimeSec: 60, editorCount: 1, windowsEmitted: 0, windowsDropped: 0 },
			{ count: 0, avg: 0, peak: 0 },
		);
		assert.equal(noFetch.text, empty.text);
	});
});

describe("formatUptime", () => {
	it("renders sub-minute as 'Ns'", () => {
		assert.equal(formatUptime(0), "0s");
		assert.equal(formatUptime(42), "42s");
	});

	it("renders sub-hour as 'Nm'", () => {
		assert.equal(formatUptime(60), "1m");
		assert.equal(formatUptime(59 * 60), "59m");
	});

	it("renders sub-day as 'Nh'", () => {
		assert.equal(formatUptime(3600), "1h");
		assert.equal(formatUptime(23 * 3600), "23h");
	});

	it("renders multi-day as 'Nd Mh' or 'Nd' when hours are zero", () => {
		assert.equal(formatUptime(86400), "1d");
		assert.equal(formatUptime(2 * 86400 + 4 * 3600), "2d 4h");
	});

	it("clamps negative values to '0s' instead of returning '-Ns'", () => {
		// Defensive — the daemon's uptime_sec should never be negative
		// but a clock skew between daemon and editor could in theory
		// produce that. Don't render "-12s" in the tooltip.
		assert.equal(formatUptime(-12), "0s");
	});
});

describe("shortRepoTail", () => {
	// Cross-language parity with the daemon's shortRepoTrail and the
	// companion's shortRepoTail. Each assertion here mirrors a case
	// in those tests so a refactor in one language can't silently
	// drift from the others.

	it("returns the last two segments for nested paths", () => {
		assert.equal(shortRepoTail("/Users/me/code/beats"), "code/beats");
	});

	it("returns the original when there are fewer than three segments", () => {
		assert.equal(shortRepoTail("a/b"), "a/b");
	});

	it("handles Windows-style backslash separators", () => {
		assert.equal(shortRepoTail("C:\\Users\\me\\code\\beats"), "code/beats");
	});

	it("collapses repeated separators", () => {
		assert.equal(shortRepoTail("//Users//me//code//beats"), "code/beats");
	});
});

// isStaleNoEmissions surfaces the "Accessibility permission revoked
// mid-session" diagnostic. The daemon's internal probe retries every
// 90s; if uptime > 90s and zero windows have been emitted, that's
// the canonical sign something's gone wrong server-side.
describe("isStaleNoEmissions", () => {
	function fakeHealth(uptimeSec: number, windowsEmitted: number, windowsDropped = 0) {
		return {
			ok: true,
			version: "v1.0.0",
			uptimeSec,
			editorCount: 1,
			windowsEmitted,
			windowsDropped,
		};
	}

	it("fires when uptime crosses the 90s threshold with zero emissions", () => {
		assert.equal(isStaleNoEmissions(fakeHealth(120, 0)), true);
		assert.equal(isStaleNoEmissions(fakeHealth(90, 0)), true);
	});

	it("does not fire on a freshly-started daemon", () => {
		// 60s old, 0 emitted — the daemon hasn't had time to flush
		// even one window yet (windows are 60s each). False alarm.
		assert.equal(isStaleNoEmissions(fakeHealth(60, 0)), false);
	});

	it("does not fire when at least one window has been emitted", () => {
		// Once any data has flowed, the pipeline is known-good. Even
		// a long quiet stretch shouldn't re-trigger the diagnostic
		// (the user just stopped working — that's not a system fault).
		assert.equal(isStaleNoEmissions(fakeHealth(3600, 1)), false);
	});

	it("formatStatusBar appends the diagnostic hint to the tooltip", () => {
		const { tooltip } = formatStatusBar(fakeHealth(120, 0));
		assert.match(tooltip, /no flow windows emitted/i);
		assert.match(tooltip, /Accessibility permission/);
	});

	it("formatStatusBar omits the hint on a healthy daemon", () => {
		// Healthy daemon producing data — no diagnostic, no noise.
		const { tooltip } = formatStatusBar(fakeHealth(3600, 60));
		assert.doesNotMatch(tooltip, /no flow windows emitted/i);
	});

	it("formatStatusBar surfaces a non-zero windows_dropped count", () => {
		// Producing-but-not-landing pipeline: 60 emitted, 5 dropped.
		// Tooltip should flag the dropped count without false-alarming
		// the Accessibility diagnostic (windows are still emitting).
		const { tooltip } = formatStatusBar(fakeHealth(3600, 60, 5));
		assert.match(tooltip, /5 windows dropped/);
		assert.match(tooltip, /API reachability/);
		// Still healthy on the Accessibility axis — no false alarm.
		assert.doesNotMatch(tooltip, /no flow windows emitted/i);
	});

	it("formatStatusBar omits the dropped chunk when the count is zero", () => {
		// Healthy state — no spurious "0 dropped" line on every poll.
		const { tooltip } = formatStatusBar(fakeHealth(3600, 60, 0));
		assert.doesNotMatch(tooltip, /windows dropped/i);
	});
});
