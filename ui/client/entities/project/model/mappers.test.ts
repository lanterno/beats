import { describe, expect, it } from "vitest";
import type { ApiContractWeek, ApiProject } from "@/shared/api";
import { toApiProject, toContractWeek, toProject } from "./mappers";

describe("Project mapper round-trip", () => {
	it("preserves the previously-invisible fields across toProject → toApiProject", () => {
		// P1.1 guard: without these mapped, any form using updateProject would
		// PUT { github_repo: undefined } and the backend would clobber the value
		// — the exact silent-wipe bug class the contract revamp is fixing.
		const fromWire: ApiProject = {
			id: "p1",
			name: "Alpha",
			description: "x",
			color: "#FBBF24",
			archived: false,
			weekly_goal: 10,
			goal_type: "target",
			goal_overrides: [],
			github_repo: "lanterno/beats",
			category: "coding",
			autostart_repos: ["/Users/me/code/beats"],
			kind: "side_project",
		};

		const domain = toProject(fromWire);
		expect(domain.githubRepo).toBe("lanterno/beats");
		expect(domain.category).toBe("coding");
		expect(domain.autostartRepos).toEqual(["/Users/me/code/beats"]);

		const backToWire = toApiProject(domain);
		expect(backToWire.github_repo).toBe("lanterno/beats");
		expect(backToWire.category).toBe("coding");
		expect(backToWire.autostart_repos).toEqual(["/Users/me/code/beats"]);
	});

	it("normalizes absent values: undefined on the domain side, null/[] on the wire", () => {
		const fromWire: ApiProject = {
			id: "p2",
			name: "Beta",
			archived: false,
			goal_type: "target",
			goal_overrides: [],
			autostart_repos: [],
			kind: "side_project",
		};
		const domain = toProject(fromWire);
		expect(domain.githubRepo).toBeUndefined();
		expect(domain.category).toBeUndefined();
		expect(domain.autostartRepos).toEqual([]);

		const backToWire = toApiProject(domain);
		expect(backToWire.github_repo).toBeNull();
		expect(backToWire.category).toBeNull();
		expect(backToWire.autostart_repos).toEqual([]);
	});

	it("carries a day job's contract both ways, and none on any other kind", () => {
		const fromWire: ApiProject = {
			id: "p3",
			name: "Employer",
			archived: false,
			goal_type: "target",
			goal_overrides: [],
			autostart_repos: [],
			kind: "day_job",
			contract: {
				terms: [
					{
						effective_from: "2026-01-05",
						schedule_type: "part_time",
						full_time_hours: 42,
						percentage: 0.8,
						weekly_hours: null,
						note: null,
					},
				],
				holiday_country: "CH",
				holiday_subdivision: "ZH",
				opening_balance_hours: 4.5,
				ended_on: null,
			},
		};
		const domain = toProject(fromWire);
		expect(domain.kind).toBe("day_job");
		expect(domain.contract).toEqual({
			terms: [
				{
					effectiveFrom: "2026-01-05",
					scheduleType: "part_time",
					fullTimeHours: 42,
					percentage: 0.8,
				},
			],
			holidayCountry: "CH",
			holidaySubdivision: "ZH",
			openingBalanceHours: 4.5,
		});
		expect(toApiProject(domain).contract).toEqual(fromWire.contract);

		// The wire never carries a contract on a side project; should one
		// arrive, reading it would let the UI show a contract the API ignores.
		const stray = toProject({ ...fromWire, kind: "side_project" });
		expect(stray.contract).toBeUndefined();
		expect(toApiProject(stray).contract).toBeNull();
	});
});

describe("toContractWeek", () => {
	it("keeps the wire's null as no expectation, not 0, and drops the nulls on a day", () => {
		// An objective week: the API says null for expected, remaining and
		// balance, which the card must read as "none" — read as 0 it would
		// show "Expected 0.0 h" and the header "12.0/0.0h".
		const fromWire: ApiContractWeek = {
			week_of: "2026-04-06",
			expected: null,
			worked: 12,
			remaining: null,
			balance: null,
			days: [
				{ date: "2026-04-06", expected: 0, worked: 4, holiday: null, absence: null },
				{
					date: "2026-04-07",
					expected: 0,
					worked: 0,
					absence: { type: "sick", half_day: true, note: null },
				},
				{ date: "2026-04-08", expected: 0, worked: 8, holiday: "Easter Monday" },
			],
		};
		expect(toContractWeek(fromWire)).toEqual({
			weekOf: "2026-04-06",
			expected: undefined,
			worked: 12,
			remaining: undefined,
			balance: undefined,
			days: [
				{ date: "2026-04-06", expected: 0, worked: 4, holiday: undefined, absence: undefined },
				{
					date: "2026-04-07",
					expected: 0,
					worked: 0,
					holiday: undefined,
					absence: { type: "sick", halfDay: true, note: undefined },
				},
				{
					date: "2026-04-08",
					expected: 0,
					worked: 8,
					holiday: "Easter Monday",
					absence: undefined,
				},
			],
		});
	});
});
