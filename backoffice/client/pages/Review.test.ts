import { describe, expect, it } from "vitest";
import { commandSpec } from "@/shared/commands";
import { sent } from "./Review";

const limits = () => commandSpec("account.set_limits");
const suspend = () => commandSpec("account.suspend");

describe("sent", () => {
	it("sends nothing extra for a command with no fields", () => {
		expect(sent(commandSpec("account.sign_out_everywhere"), { stray: 1 })).toEqual({});
		expect(sent(undefined, { stray: 1 })).toEqual({});
	});

	// An empty box means the platform's default, and the API reads null as
	// that. Sending 0 would set a ceiling of zero writes a minute.
	it("turns an empty box into null, never zero", () => {
		const out = sent(limits(), {
			coach_monthly_budget_usd: "",
			writes_per_minute_beats: "",
			writes_per_minute_signals: "",
			imports_per_hour: "",
			webhooks_disabled: false,
		});
		expect(out).toEqual({
			coach_monthly_budget_usd: null,
			writes_per_minute_beats: null,
			writes_per_minute_signals: null,
			imports_per_hour: null,
			webhooks_disabled: false,
		});
	});

	it("sends a number as a number, not the typed string", () => {
		const out = sent(limits(), { writes_per_minute_beats: "20", webhooks_disabled: false });
		expect(out.writes_per_minute_beats).toBe(20);
	});

	// The flag is always sent: leaving it out would read as "no change",
	// and set_limits writes the whole document at once.
	it("always sends the flag, both ways", () => {
		expect(sent(limits(), { webhooks_disabled: true }).webhooks_disabled).toBe(true);
		expect(sent(limits(), {}).webhooks_disabled).toBe(false);
	});

	it("keeps text as it was typed", () => {
		expect(sent(suspend(), { reason: "scraping the API" })).toEqual({
			reason: "scraping the API",
		});
	});
});

describe("what will change", () => {
	// The row that justifies the whole page: saving limits with the boxes
	// empty clears a cap that is already set, and the operator should see
	// that before pressing the button rather than afterwards.
	it("shows an existing cap being cleared by an empty box", () => {
		const rows = limits()?.changes(
			{ overridden: true, coach_monthly_budget_usd: 50 },
			{ coach_monthly_budget_usd: "", webhooks_disabled: false },
		);
		const coach = rows?.find((r) => r.what === "Coach budget");
		expect(coach).toEqual({ what: "Coach budget", now: "50 a month", after: "Platform default" });
	});

	it("shows a cap being set where there was none", () => {
		const rows = limits()?.changes(
			{ overridden: false },
			{ coach_monthly_budget_usd: "25", webhooks_disabled: false },
		);
		expect(rows?.find((r) => r.what === "Coach budget")).toEqual({
			what: "Coach budget",
			now: "Platform default",
			after: "25 a month",
		});
	});

	it("reads the webhook flag on both sides", () => {
		const rows = limits()?.changes({ webhooks_disabled: true }, { webhooks_disabled: false });
		expect(rows?.find((r) => r.what === "Webhooks")).toEqual({
			what: "Webhooks",
			now: "Off",
			after: "On",
		});
	});

	it("names the kind an account is suspended for when unsuspending", () => {
		const rows = commandSpec("account.unsuspend")?.changes(
			{ suspended: true, suspended_kind: "abuse" },
			{},
		);
		expect(rows?.[0].now).toBe("Suspended for abuse");
		expect(rows?.[0].after).toBe("Active");
	});

	// `describe()` answers {exists: false} for an account that is not there.
	// The specs read a state they were handed; it is the page that must not
	// show the table at all in that case, which `missing` holds — pinned
	// here so the two stay in step if a spec ever grows a row of its own.
	it("would read a missing subject as active, which is why the page hides it", () => {
		const rows = commandSpec("account.suspend")?.changes({ exists: false }, {});
		expect(rows?.[0].now).toBe("Active");
	});
});

describe("the command specs", () => {
	// Every act the account page offers has to have copy here, or the review
	// would open on an empty page.
	it("gives every account command a name, an action and both fixed answers", () => {
		for (const name of [
			"account.set_limits",
			"account.clear_limits",
			"account.sign_out_everywhere",
			"account.suspend",
			"account.unsuspend",
			"account.erase",
		]) {
			const spec = commandSpec(name);
			expect(spec, name).toBeDefined();
			expect(spec?.title).toBeTruthy();
			expect(spec?.action).toBeTruthy();
			expect(spec?.notices).toBeTruthy();
			expect(spec?.undo).toBeTruthy();
		}
	});

	it("marks suspension and erasure as the grave ones", () => {
		expect(commandSpec("account.suspend")?.grave).toBe(true);
		expect(commandSpec("account.erase")?.grave).toBe(true);
		expect(commandSpec("account.sign_out_everywhere")?.grave).toBeUndefined();
	});
});
