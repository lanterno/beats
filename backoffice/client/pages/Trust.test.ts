import { describe, expect, it } from "vitest";
import type { AbuseReport, SignupWave } from "@/shared/api/schema";
import { AXES, axisNote, axisRows, trustHeadline, waveSentence, waveTitle } from "./Trust";

const KEY = "0123456789abcdef0123456789abcdef";

const wave = (fields: Partial<SignupWave>): SignupWave => ({
	hour: "2026-11-14T09",
	completed: 0,
	usual: 0,
	accounts_with_writes: 0,
	largest_group: null,
	largest_key: null,
	...fields,
});

describe("trustHeadline", () => {
	it("says a network stands out only when the signal shows one", () => {
		expect(
			trustHeadline(wave({ completed: 84, usual: 14, largest_group: 71, largest_key: KEY })),
		).toBe("One network stands out in this hour's sign-ups.");
		expect(trustHeadline(wave({ completed: 9, usual: 4 }))).toBe(
			"More people are signing up than usual this hour.",
		);
		expect(trustHeadline(wave({ completed: 4, usual: 4 }))).toBe(
			"This hour's sign-ups are ordinary.",
		);
	});

	it("judges nothing it was not sent", () => {
		expect(trustHeadline(null)).toBe("Who is using far more than everyone else.");
	});
});

describe("the sign-up signal", () => {
	it("titles the hour against the usual", () => {
		expect(waveTitle(wave({ completed: 84, usual: 14 }))).toBe(
			"84 sign-ups since 09:00 UTC, usually about 14",
		);
		expect(waveTitle(wave({ completed: 1 }))).toBe("1 sign-up since 09:00 UTC, usually none");
	});

	it("says when no network is large enough to show", () => {
		expect(waveSentence(wave({ completed: 3, usual: 1.5 }))).toBe(
			"No network is large enough to show.",
		);
	});

	it("calls the largest network A, never by its key", () => {
		const said = waveSentence(
			wave({
				completed: 84,
				usual: 14,
				largest_group: 71,
				largest_key: KEY,
				accounts_with_writes: 3,
			}),
		);
		expect(said).toBe(
			"Network A is 71 of them. Of all 84 accounts created this hour, 3 have written anything; which of those are Network A's is not recorded, and will not be.",
		);
		expect(said).not.toContain(KEY);
		expect(waveTitle(wave({ largest_key: KEY }))).not.toContain(KEY);
	});
});

describe("the outlier table", () => {
	const report = {
		coach_spend_per_account: [{ user_id: "a", value: 46.1 }],
		flow_windows_per_account_today: [{ user_id: "b", value: 4210 }],
		sessions_created_7d_per_account: [],
		report_links_per_account: [{ user_id: "c", value: 64 }],
		webhook_domains: [{ domain: "hooks.example.com", value: 27 }],
		devices_per_account: [{ user_id: "d", value: 41 }],
		signups_per_day: [],
	} as AbuseReport;

	// Each tab must read its own axis: a slip here would put one count under
	// another's heading, with nothing on the page to say so.
	it("gives each tab its own axis", () => {
		expect(AXES.map((a) => axisRows(report, a.id))).toEqual([
			report.coach_spend_per_account,
			report.flow_windows_per_account_today,
			report.sessions_created_7d_per_account,
			report.report_links_per_account,
			report.webhook_domains,
			report.devices_per_account,
		]);
	});

	it("says how many it shows, and over what", () => {
		expect(axisNote("coach", 4)).toBe("The highest 4 this month.");
		expect(axisNote("flow", 1)).toBe("The only one today.");
		expect(axisNote("sessions", 0)).toBe("Nothing to rank in the last 7 days.");
	});
});
