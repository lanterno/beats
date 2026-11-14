import { describe, expect, it } from "vitest";
import { accessHeadline, controlRows, controlState } from "./Access";

const control = (name: string, fields: Record<string, unknown>) => ({
	name,
	network: null,
	in_force: true,
	until: null,
	value: null,
	reason: null,
	set_by: null,
	set_at: null,
	...fields,
});

describe("accessHeadline", () => {
	it("counts people and operators", () => {
		expect(accessHeadline([])).toBe("Nobody is on the allowlist.");
		expect(accessHeadline([{ email: "a", role: "operator" }])).toBe("One person can reach this.");
		expect(
			accessHeadline([
				{ email: "a", role: "operator" },
				{ email: "b", role: "viewer" },
			]),
		).toBe("2 people can reach this, one of them an operator.");
	});
});

describe("controlState", () => {
	it("reads an absent or expired control as open", () => {
		expect(controlState("coach", undefined)).toBe("Running");
		expect(controlState("imports_per_hour", undefined)).toBe("No limit");
		expect(controlState("coach", control("coach", { in_force: false }))).toBe("Running");
	});

	it("says until when a pause ends, and a limit's value", () => {
		expect(controlState("coach", control("coach", { until: "2026-11-21T09:00:00+00:00" }))).toBe(
			"Paused until 2026-11-21 09:00",
		);
		expect(controlState("imports_per_hour", control("imports_per_hour", { value: 10 }))).toBe(
			"10 an hour",
		);
	});

	it("tells slowed sign-ups from paused ones", () => {
		const slowed = control("signups", { value: 20, until: "2026-11-15T00:00:00+00:00" });
		expect(controlState("signups", slowed)).toBe("Slowed to 20 an hour, until 2026-11-15 00:00");
		expect(
			controlState("signups", control("signups", { until: "2026-11-15T00:00:00+00:00" })),
		).toBe("Paused until 2026-11-15 00:00");
	});
});

describe("controlRows", () => {
	const KEY = "9f2c4e1a7b3d5f60";
	const network = (key: string, fields: Record<string, unknown> = {}) =>
		control("signups", { network: key, value: 5, until: "2026-11-15T00:00:00+00:00", ...fields });

	// The read sorts everyone's control first, but there may be none: a
	// network's slow-down must not stand in for it, or its Clear would lift
	// the wrong one.
	it("never reads a network's slow-down as the control for everyone", () => {
		const rows = controlRows(["signups"], [network(KEY)]);
		expect(rows[0]).toEqual({ name: "signups", control: undefined, network: null });
		expect(controlState("signups", rows[0].control)).toBe("Running");
	});

	it("gives everyone's control and each network in force a row of its own", () => {
		const everyone = control("signups", { value: 50, until: "2026-11-20T00:00:00+00:00" });
		const rows = controlRows(
			["coach", "signups"],
			[control("coach", { in_force: false }), everyone, network(KEY), network("0123456789abcdef")],
		);
		expect(rows.map((r) => [r.name, r.network])).toEqual([
			["coach", null],
			["signups", null],
			["signups", KEY],
			["signups", "0123456789abcdef"],
		]);
		expect(rows[1].control).toBe(everyone);
	});

	it("leaves out a network's slow-down that has ended", () => {
		const rows = controlRows(["signups"], [network(KEY, { in_force: false })]);
		expect(rows.map((r) => r.network)).toEqual([null]);
	});
});
