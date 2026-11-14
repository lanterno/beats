import { describe, expect, it } from "vitest";
import { type FieldProblem, OperatorApiError } from "@/shared/api/client";
import { type CommandField, commandSpec, fieldsOf, startingArgs } from "@/shared/commands";
import { refusalOf, requestArgs, sent } from "./Review";

const limits = () => commandSpec("account.set_limits");
const fields = (name: string, subject = "x"): CommandField[] => {
	const spec = commandSpec(name);
	return spec ? fieldsOf(spec, subject) : [];
};

describe("sent", () => {
	it("sends nothing extra for a command with no fields", () => {
		expect(sent(fields("account.sign_out_everywhere"), { stray: 1 })).toEqual({});
		expect(sent([], { stray: 1 })).toEqual({});
	});

	// An empty box means the field's default, and the API reads a field left
	// out as that. Sending 0 would set a ceiling of zero writes a minute.
	it("leaves an empty box out, never zero", () => {
		const out = sent(fields("account.set_limits"), {
			coach_monthly_budget_usd: "",
			writes_per_minute_beats: " ",
			writes_per_minute_signals: "",
			imports_per_hour: "",
			webhooks_disabled: false,
		});
		expect(out).toEqual({ webhooks_disabled: false });
	});

	// Not null: the status models have defaults that are not None (the fixed
	// all-clear, no parts), and refuse null, so the review could never open.
	it("leaves an empty status message and empty parts out", () => {
		expect(sent(fields("status.clear", "public"), { message: "" })).toEqual({});
		expect(
			sent(fields("status.publish", "public"), {
				state: "degraded",
				message: "Syncing is slow",
				affected: "",
			}),
		).toEqual({ state: "degraded", message: "Syncing is slow" });
	});

	// NaN goes over JSON as null, and a slow-down sent as null is a pause.
	it("sends a number box that is not a number as typed, for the API to refuse", () => {
		const out = sent(fields("account.set_limits"), {
			writes_per_minute_beats: "1,000",
			imports_per_hour: "10/h",
			webhooks_disabled: false,
		});
		expect(out.writes_per_minute_beats).toBe("1,000");
		expect(out.imports_per_hour).toBe("10/h");
	});

	it("sends a number as a number, not the typed string", () => {
		const out = sent(fields("account.set_limits"), {
			writes_per_minute_beats: "20",
			webhooks_disabled: false,
		});
		expect(out.writes_per_minute_beats).toBe(20);
	});

	// The flag is always sent: leaving it out would read as "no change",
	// and set_limits writes the whole document at once.
	it("always sends the flag, both ways", () => {
		expect(sent(fields("account.set_limits"), { webhooks_disabled: true }).webhooks_disabled).toBe(
			true,
		);
		expect(sent(fields("account.set_limits"), {}).webhooks_disabled).toBe(false);
	});

	it("keeps text as it was typed", () => {
		expect(sent(fields("account.suspend"), { reason: "scraping the API" })).toEqual({
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
			"u",
		);
		const coach = rows?.find((r) => r.what === "Coach budget");
		expect(coach).toEqual({ what: "Coach budget", now: "50 a month", after: "Platform default" });
	});

	it("shows a cap being set where there was none", () => {
		const rows = limits()?.changes(
			{ overridden: false },
			{ coach_monthly_budget_usd: "25", webhooks_disabled: false },
			"u",
		);
		expect(rows?.find((r) => r.what === "Coach budget")).toEqual({
			what: "Coach budget",
			now: "Platform default",
			after: "25 a month",
		});
	});

	it("reads the webhook flag on both sides", () => {
		const rows = limits()?.changes({ webhooks_disabled: true }, { webhooks_disabled: false }, "u");
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
			"u",
		);
		expect(rows?.[0].now).toBe("Suspended for abuse");
		expect(rows?.[0].after).toBe("Active");
	});

	// `describe()` answers {exists: false} for an account that is not there.
	// The specs read a state they were handed; it is the page that must not
	// show the table at all in that case, which `missing` holds — pinned
	// here so the two stay in step if a spec ever grows a row of its own.
	it("would read a missing subject as active, which is why the page hides it", () => {
		const rows = commandSpec("account.suspend")?.changes({ exists: false }, {}, "u");
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

describe("the control commands", () => {
	// One control.set serves every control, so what it asks for depends on
	// the subject: a limit a value, a pause an end and a reason, sign-ups
	// either.
	it("asks a pause for an end and a reason, and a limit for a value", () => {
		expect(fields("control.set", "coach").map((f) => f.key)).toEqual(["until", "reason"]);
		expect(fields("control.set", "writes_per_minute_beats").map((f) => f.key)).toEqual(["value"]);
		expect(fields("control.set", "signups").map((f) => f.key)).toEqual([
			"until",
			"reason",
			"value",
			"network",
		]);
	});

	it("says what a pause and a limit will become", () => {
		const set = commandSpec("control.set");
		expect(
			set?.changes({ set: false }, { until: "2026-11-21T09:00:00Z", reason: "r" }, "coach"),
		).toEqual([{ what: "Coach", now: "Running", after: "Paused until 2026-11-21T09:00" }]);
		expect(set?.changes({ set: false }, { value: 120 }, "writes_per_minute_beats")).toEqual([
			{ what: "Beat writes per account", now: "No limit", after: "120 a minute" },
		]);
		expect(
			set?.changes(
				{ set: true, in_force: true, until: "2026-11-15T00:00:00+00:00", value: 20 },
				{ until: "2026-11-16T00:00:00Z", reason: "r", value: 10 },
				"signups",
			),
		).toEqual([
			{
				what: "Sign-ups",
				now: "Slowed to 20 an hour",
				after: "Slowed to 10 an hour until 2026-11-16T00:00",
			},
		]);
	});

	// An expired pause is open to the API but its document is still there;
	// the review must read it as running, not as paused.
	it("reads an expired pause as running", () => {
		const clear = commandSpec("control.clear");
		expect(
			clear?.changes(
				{ set: true, in_force: false, until: "2026-11-01T00:00:00+00:00" },
				{},
				"imports",
			),
		).toEqual([{ what: "Imports", now: "Running", after: "Running" }]);
	});
});

describe("the deploy commands", () => {
	it("say the web app is not held, before and after", () => {
		const rows = commandSpec("deploy.freeze")?.changes(
			{ frozen: false },
			{ until: "2026-11-15T09:00:00Z", reason: "r" },
			"api",
		);
		expect(rows).toEqual([
			{ what: "API deploys", now: "Shipping", after: "Frozen until 2026-11-15T09:00" },
			{ what: "Web app deploys", now: "Shipping", after: "Still shipping" },
		]);
		expect(commandSpec("deploy.freeze")?.about).toContain("The web app can still ship");
	});

	it("send no subject: the freeze is the platform's", () => {
		expect(commandSpec("deploy.freeze")?.subjectless).toBe(true);
		expect(commandSpec("deploy.unfreeze")?.subjectless).toBe(true);
	});
});

describe("the status commands", () => {
	it("show exactly what will go public, before and after", () => {
		const rows = commandSpec("status.publish")?.changes(
			{ published: true, state: "degraded", message: "Slow.", affected: ["coach"] },
			{ state: "outage", message: "Down.", affected: "coach, api" },
			"public",
		);
		expect(rows).toEqual([
			{ what: "What customers see", now: "degraded: Slow.", after: "outage: Down." },
			{ what: "Affected", now: "coach", after: "coach, api" },
		]);
	});

	it("send no subject: the file is the platform's", () => {
		expect(commandSpec("status.publish")?.subjectless).toBe(true);
		expect(commandSpec("status.clear")?.subjectless).toBe(true);
	});
});

describe("refusalOf", () => {
	const refused = (...problems: Array<Omit<FieldProblem, "type"> & { type?: string }>) =>
		new OperatorApiError(
			422,
			"Validation failed",
			"INVALID_COMMAND_ARGS",
			problems.map((p) => ({ type: "value_error", ...p })),
		);
	const log = fields("erasure_request.log", "new");

	// Every box filled, and the old page still said "fill in the fields".
	it("puts a filled box's refusal beside it, in the API's words", () => {
		const reason = "a reference must not be an address; name the account by its id";
		const out = refusalOf(refused({ path: "reference", message: reason }), log, {
			reference: "ana@example.test",
			received_on: "2026-11-01",
		});
		expect(out).toEqual({ byField: { reference: reason }, general: [], incomplete: false });
	});

	it("asks for the rest only when a required box is really empty", () => {
		const out = refusalOf(
			refused({ path: "received_on", message: "Field required", type: "missing" }),
			log,
			{ reference: "T-1", received_on: " " },
		);
		expect(out).toEqual({ byField: {}, general: [], incomplete: true });
	});

	it("says a rule on the arguments as a whole by the button", () => {
		const out = refusalOf(
			refused({ path: "", message: "a pause lasts at most 7 days; set it again after" }),
			fields("control.set", "coach"),
			{ until: "2026-12-30T00:00:00Z", reason: "r" },
		);
		expect(out.general).toEqual(["a pause lasts at most 7 days; set it again after"]);
		expect(out.byField).toEqual({});
	});

	it("reads a list item's path as its box", () => {
		const out = refusalOf(
			refused({ path: "affected.1", message: "Input should be 'web app', 'api' or …" }),
			fields("status.publish", "public"),
			{ state: "outage", message: "Down.", affected: "api, apii" },
		);
		expect(Object.keys(out.byField)).toEqual(["affected"]);
	});

	it("reads anything but a 422 as no refusal of the arguments", () => {
		const missing = new OperatorApiError(404, "Account not found", "ACCOUNT_NOT_FOUND");
		expect(refusalOf(missing, log, {})).toEqual({ byField: {}, general: [], incomplete: false });
	});
});

describe("startingArgs", () => {
	const link = (query: string) => (key: string) => new URLSearchParams(query).get(key);
	const start = (name: string, subject: string, query: string) => {
		const spec = commandSpec(name);
		return spec ? startingArgs(spec, subject, link(query)) : {};
	};

	// A crafted link must not open a post already written, one click from
	// going public.
	it("fills nothing that is said or decided from a link", () => {
		expect(start("status.publish", "public", "state=outage&message=Hacked&affected=api")).toEqual({
			state: "",
			message: "",
			affected: "",
		});
	});

	it("fills the box that names what is acted on, and only that", () => {
		const args = start("control.set", "signups", "network=k3y-0f-net&reason=forged&value=1");
		expect(args.network).toBe("k3y-0f-net");
		expect([args.reason, args.value, args.until]).toEqual(["", "", ""]);
	});
});

describe("the subject a review sends", () => {
	const purge = commandSpec("retention.purge");

	// "all" sent as an organisation id would be refused as no such
	// organisation, and the platform-wide purge could never be queued.
	it("sends a purge of every organisation as no organisation at all", () => {
		expect(purge && requestArgs(purge, "all", {})).toEqual({});
		expect(purge && requestArgs(purge, "6730aaa2b3c4d5e6f7a8b9c1", {})).toEqual({
			organisation_id: "6730aaa2b3c4d5e6f7a8b9c1",
		});
	});

	it("sends a device with the account it belongs to", () => {
		const revoke = commandSpec("device.revoke");
		expect(revoke && requestArgs(revoke, "u1", { device_id: "d1" })).toEqual({
			user_id: "u1",
			device_id: "d1",
		});
	});
});

describe("what a subject that is not there reads as", () => {
	// `describe()` answers None for a device of another account and for a
	// requester who is not a member. Read as falsy, either would look like
	// the ordinary state the act expects.
	it("tells a device not on the account from one that is paired", () => {
		const now = (revoked: unknown) =>
			commandSpec("device.revoke")?.changes({ revoked }, {}, "u")[0].now;
		expect(now(null)).not.toBe(now(false));
		expect(now(null)).not.toBe(now(true));
	});

	it("tells a requester who is not a member from one who is", () => {
		const now = (role: unknown) =>
			commandSpec("organisation.grant_owner")?.changes({ requester_role: role }, {}, "o")[1].now;
		expect(now(null)).not.toBe(now("member"));
	});
});
