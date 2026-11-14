import { describe, expect, it } from "vitest";
import type { OrganisationSummary } from "@/shared/api/schema";
import { deletionOf, deletionReady, highestRole, standing } from "./organisations";

const NOW = new Date("2026-11-14T12:00:00Z");

const org = (over: Partial<OrganisationSummary> = {}): OrganisationSummary => ({
	id: "o1",
	name: "Harbour",
	created_at: "2025-02-14T00:00:00Z",
	owners: 1,
	all_owners_suspended: false,
	closes_on: null,
	members_by_role: { owner: 1, member: 4 },
	active_assignments: 3,
	retention_years: null,
	...over,
});

const deletion = { id: "j1", run_after: "2026-11-15T06:00:00Z" };

describe("standing", () => {
	it("needs you when nobody owns it and nothing is under way yet", () => {
		expect(standing(org({ owners: 0 }), null, NOW).group).toBe("needs");
	});

	// The operator has already acted on an ownerless one that is closing or
	// being deleted: it is on its way out, not waiting.
	it("is leaving once a closing or a deletion is under way, owner or not", () => {
		expect(standing(org({ owners: 0, closes_on: "2026-12-30" }), null, NOW).group).toBe("leaving");
		expect(standing(org({ owners: 0 }), deletion, NOW).state.label).toBe("Deleting in 18 h");
		expect(standing(org({ closes_on: "2026-12-30" }), null, NOW).group).toBe("leaving");
	});

	// A suspended owner is still the owner: watched, never "Needs you".
	it("watches an organisation whose every owner is suspended rather than asking you to act", () => {
		const s = standing(org({ all_owners_suspended: true }), null, NOW);
		expect(s.group).toBe("needs");
		expect(s.state.label).toBe("Watching");
	});

	it("says a deletion past its window is happening now, not in a negative number of hours", () => {
		const late = { id: "j1", run_after: "2026-11-14T11:00:00Z" };
		expect(standing(org({ owners: 0 }), late, NOW).state.label).toBe("Deleting now");
	});
});

describe("deletionOf", () => {
	const job = (over: Record<string, unknown>) => ({
		id: "j1",
		command: "organisation.delete",
		subject_id: "o1",
		state: "queued",
		run_after: "2026-11-15T06:00:00Z",
		...over,
	});

	it("finds the deletion waiting on this organisation, queued or running", () => {
		expect(deletionOf([job({})], "o1")?.id).toBe("j1");
		expect(deletionOf([job({ state: "running" })], "o1")?.id).toBe("j1");
	});

	it("ignores one that is over, another organisation's, and a purge of this one", () => {
		expect(deletionOf([job({ state: "cancelled" }), job({ state: "done" })], "o1")).toBeNull();
		expect(deletionOf([job({ subject_id: "o2" })], "o1")).toBeNull();
		expect(deletionOf([job({ command: "retention.purge" })], "o1")).toBeNull();
	});
});

describe("highestRole", () => {
	it("reads the ladder, not the order the API listed the roles in", () => {
		expect(highestRole({ member: 9, manager: 1, admin: 2 })).toBe("Admin, 2 people");
		expect(highestRole({ member: 1 })).toBe("Member, 1 person");
	});

	it("skips a role nobody holds, and says nobody when no one is left", () => {
		expect(highestRole({ owner: 0, viewer: 3 })).toBe("Viewer, 3 people");
		expect(highestRole({})).toBe("Nobody");
	});
});

describe("deletionReady", () => {
	// Queued now, it runs a day later; the closing day must have come by then.
	it("offers the deletion from the day before the closing day", () => {
		expect(deletionReady("2026-11-15", NOW)).toBe(true);
		expect(deletionReady("2026-11-16", NOW)).toBe(false);
		expect(deletionReady("2026-11-01", NOW)).toBe(true);
	});

	it("never offers it for an organisation that is not closing", () => {
		expect(deletionReady(null, NOW)).toBe(false);
	});
});
