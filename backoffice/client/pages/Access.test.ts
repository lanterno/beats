import { describe, expect, it } from "vitest";
import { accessHeadline, controlState } from "./Access";

const control = (name: string, fields: Record<string, unknown>) => ({
	name,
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
