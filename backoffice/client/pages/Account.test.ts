import { describe, expect, it } from "vitest";
import type { AccountDetail } from "@/shared/api/schema";
import { accountHeadline } from "./Account";

const account = (over: Partial<AccountDetail> = {}): AccountDetail =>
	({
		id: "6730f1a2b3c4d5e6f7a8b9c0",
		email: "maya@example.com",
		created_at: null,
		last_seen_on: null,
		suspended_at: null,
		suspended_kind: null,
		suspended_by: null,
		sessions_valid_after: null,
		passkeys: 0,
		projects: 0,
		sessions: 0,
		biometric_rows: 0,
		storage_bytes: 0,
		coach_spend_usd: 0,
		coach_budget_usd: null,
		limits_overridden: false,
		...over,
	}) as AccountDetail;

describe("accountHeadline", () => {
	it("says nothing needs you when nothing does", () => {
		expect(accountHeadline(account())).toBe("Nothing about this account needs you.");
	});

	it("leads with the suspension, and names its kind", () => {
		expect(accountHeadline(account({ suspended_at: "2026-11-01T00:00:00Z" }))).toBe(
			"This account is suspended.",
		);
		expect(
			accountHeadline(account({ suspended_at: "2026-11-01T00:00:00Z", suspended_kind: "abuse" })),
		).toBe("This account is suspended for abuse.");
	});

	// A suspended account near its cap is suspended first: the cap stopped
	// mattering the moment it could not sign in.
	it("puts the suspension above the coach cap", () => {
		const both = account({
			suspended_at: "2026-11-01T00:00:00Z",
			coach_budget_usd: 50,
			coach_spend_usd: 49,
		});
		expect(accountHeadline(both)).toBe("This account is suspended.");
	});

	// 80% is the line the landing page counts an account at, so the two must
	// agree about what "near" means.
	it("turns at 80% of the cap and not before", () => {
		expect(accountHeadline(account({ coach_budget_usd: 50, coach_spend_usd: 39.99 }))).toBe(
			"Nothing about this account needs you.",
		);
		expect(accountHeadline(account({ coach_budget_usd: 50, coach_spend_usd: 40 }))).toBe(
			"This account is near its coach cap.",
		);
	});

	it("says the cap is spent once it is reached or passed", () => {
		expect(accountHeadline(account({ coach_budget_usd: 50, coach_spend_usd: 50 }))).toBe(
			"This account has spent its coach cap for the month.",
		);
		expect(accountHeadline(account({ coach_budget_usd: 50, coach_spend_usd: 61 }))).toBe(
			"This account has spent its coach cap for the month.",
		);
	});

	// No cap is the common case, and dividing by it would read as spent.
	it("says nothing about a cap that is not set, however much was spent", () => {
		expect(accountHeadline(account({ coach_budget_usd: null, coach_spend_usd: 900 }))).toBe(
			"Nothing about this account needs you.",
		);
		expect(accountHeadline(account({ coach_budget_usd: 0, coach_spend_usd: 900 }))).toBe(
			"Nothing about this account needs you.",
		);
	});
});
