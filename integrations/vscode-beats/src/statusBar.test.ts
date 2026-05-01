// Tests for formatStatusBar / formatUptime. Pure helpers — no vscode
// import — so they run under `node --test` like insightsUrl.test.ts.

import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import { formatStatusBar, formatUptime } from "./statusBar";

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
			editorCount: 1,
		});
		assert.match(text, /\$\(circle-slash\)/);
	});

	it("connected: shows the zap icon and the daemon version in the tooltip", () => {
		const { text, tooltip } = formatStatusBar({
			ok: true,
			version: "v1.2.3",
			uptimeSec: 3600,
			editorCount: 1,
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
			editorCount: 1,
		});
		assert.match(single.tooltip, /1 editor /);

		const multiple = formatStatusBar({
			ok: true,
			version: "dev",
			uptimeSec: 60,
			editorCount: 2,
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
			editorCount: 0,
		});
		assert.match(tooltip, /\(dev\)/);
	});

	it("connected with summary: shows the avg score in the status text", () => {
		const { text, tooltip } = formatStatusBar(
			{ ok: true, version: "v1.0.0", uptimeSec: 60, editorCount: 1 },
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
			{ ok: true, version: "v1.0.0", uptimeSec: 60, editorCount: 1 },
			{ count: 0, avg: 0, peak: 0 },
		);
		assert.equal(text, "$(zap) Beats");
		assert.doesNotMatch(tooltip, /Today/);
	});

	it("connected with no summary fetched: same as plain 'Beats'", () => {
		// Distinct from "summary fetched but empty" — this is the path
		// where the daemon returned 503 (no fetcher) or 502 (upstream
		// failed). The status text and the no-summary case should be
		// identical so a transient API blip doesn't reshape the bar.
		const noFetch = formatStatusBar(
			{ ok: true, version: "v1.0.0", uptimeSec: 60, editorCount: 1 },
			null,
		);
		const empty = formatStatusBar(
			{ ok: true, version: "v1.0.0", uptimeSec: 60, editorCount: 1 },
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
