import { describe, expect, it } from "vitest";
import { freshness, healthHeadline, instancesOf, percent } from "./health";

const report = (fields: Record<string, unknown>) => ({
	state: "live" as const,
	as_of: "2026-11-14T10:00:00Z",
	age_seconds: 0,
	max_instances: 2,
	availability_target: 0.995,
	figures: { availability: 0.9991, error_share: 0.004, p95_latency_ms: 420, instances: 1 },
	...fields,
});

describe("percent", () => {
	it("reads no data as no data, never as zero", () => {
		expect(percent(null)).toBe("no data");
		expect(percent(0)).toBe("0.00%");
		expect(percent(0.9983)).toBe("99.83%");
	});
});

describe("healthHeadline", () => {
	it("says above or below the target, at the boundary too", () => {
		expect(healthHeadline(report({}))).toContain("above the 99.5% target");
		const at = report({ figures: { availability: 0.995 } });
		expect(healthHeadline(at)).toContain("above");
		const below = report({ figures: { availability: 0.99 } });
		expect(healthHeadline(below)).toContain("below the 99.5% target");
	});

	it("says unavailable, and no uptime data", () => {
		expect(healthHeadline(report({ state: "unavailable", figures: null }))).toBe(
			"Live health is unavailable here.",
		);
		expect(healthHeadline(report({ figures: { availability: null } }))).toBe("No uptime data yet.");
	});
});

describe("freshness and instances", () => {
	it("gives a stale answer its age, and a live one nothing", () => {
		expect(freshness(report({}))).toBeNull();
		expect(freshness(report({ state: "stale", age_seconds: 400 }))).toBe(
			"Google did not answer. These figures are 7 min old.",
		);
	});

	it("draws instances against the ceiling when there is one", () => {
		expect(instancesOf(report({}))).toBe("1 of 2");
		expect(instancesOf(report({ max_instances: null }))).toBe("1");
		expect(instancesOf(report({ figures: { instances: null } }))).toBe("no data");
	});
});
