import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { type FieldProblem, OperatorApiError } from "@/shared/api/client";
import {
	type CommandField,
	type CommandSpec,
	commandSpec,
	EVERY_ORGANISATION,
	fieldsOf,
	startingArgs,
} from "@/shared/commands";
import { actArgs, refusalOf, requestArgs, sent } from "./Review";

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
		const coach = (before: Record<string, unknown>, typed: string) =>
			limits()
				?.changes(before, { coach_monthly_budget_usd: typed, webhooks_disabled: false }, "u")
				.find((r) => r.what === "Coach budget");
		const cleared = coach({ overridden: true, coach_monthly_budget_usd: 50 }, "");
		expect(cleared?.now).toContain("50");
		expect(cleared?.after).toBe(coach({ overridden: false }, "")?.now);
	});

	it("shows a cap being set where there was none", () => {
		const row = limits()
			?.changes({ overridden: false }, { coach_monthly_budget_usd: "25" }, "u")
			.find((r) => r.what === "Coach budget");
		expect(row?.now).not.toContain("25");
		expect(row?.after).toContain("25");
	});

	it("reads the webhook flag on both sides", () => {
		const webhooks = (before: boolean, after: boolean) =>
			limits()
				?.changes({ webhooks_disabled: before }, { webhooks_disabled: after }, "u")
				.find((r) => r.what === "Webhooks");
		const on = webhooks(true, false);
		expect(on?.now).not.toBe(on?.after);
		expect(on?.now).toBe(webhooks(false, true)?.after);
	});

	it("names the kind an account is suspended for when unsuspending", () => {
		const rows = commandSpec("account.unsuspend")?.changes(
			{ suspended: true, suspended_kind: "abuse" },
			{},
			"u",
		);
		expect(rows?.[0].now).toContain("abuse");
	});
});

describe("the control commands", () => {
	// One control.set serves every control, so what it asks for depends on
	// the subject: a limit a value, a pause an end and a reason, sign-ups
	// either. The network a slow-down covers is handed over, never typed.
	it("asks a pause for an end and a reason, and a limit for a value", () => {
		expect(fields("control.set", "coach").map((f) => f.key)).toEqual(["until", "reason"]);
		expect(fields("control.set", "writes_per_minute_beats").map((f) => f.key)).toEqual(["value"]);
		expect(fields("control.set", "signups").map((f) => f.key)).toEqual([
			"until",
			"reason",
			"value",
		]);
	});

	it("says when a pause ends, and what a limit or a slow-down will be", () => {
		const set = commandSpec("control.set");
		const [pause] = set?.changes({ set: false }, { until: "2026-11-21T09:00:00Z" }, "coach") ?? [];
		expect(pause.after).toContain("2026-11-21T09:00");
		expect(pause.now).not.toBe(pause.after);
		const [limit] = set?.changes({ set: false }, { value: 120 }, "writes_per_minute_beats") ?? [];
		expect(limit.after).toContain("120");
		const [slowed] =
			set?.changes(
				{ set: true, in_force: true, until: "2026-11-15T00:00:00+00:00", value: 20 },
				{ until: "2026-11-16T00:00:00Z", value: 10 },
				"signups",
			) ?? [];
		expect(slowed.now).toContain("20");
		expect(slowed.after).toContain("10");
		expect(slowed.after).toContain("2026-11-16T00:00");
	});

	// The page hands the network over (shared/lib/handover.ts); the table
	// must not read a network's slow-down as the control for everyone, nor
	// show its key.
	it("says a network's slow-down covers that network alone, and never shows its key", () => {
		const network = "9f2c4e1a7b3d5f60";
		const until = "2026-11-15T00:00:00Z";
		const set = commandSpec("control.set");
		const [one] =
			set?.changes({ set: false, one_network: true }, { until, value: 5, network }, "signups") ??
			[];
		const [everyone] = set?.changes({ set: false }, { until, value: 5 }, "signups") ?? [];
		expect(one.what).not.toBe(everyone.what);
		expect(one.after).toContain("5");
		expect(JSON.stringify(one)).not.toContain(network);

		const clear = commandSpec("control.clear");
		const slowed = { set: true, in_force: true, value: 5, until };
		const [lift] = clear?.changes({ ...slowed, one_network: true }, { network }, "signups") ?? [];
		const [liftAll] = clear?.changes(slowed, {}, "signups") ?? [];
		expect(lift.what).toBe(one.what);
		expect(liftAll.what).toBe(everyone.what);
		// Lifting one network says nothing of everyone's sign-ups, which
		// may still be paused.
		expect(lift.after).not.toBe(liftAll.after);
	});

	// An expired pause is open to the API but its document is still there;
	// the review must read it as running, not as paused.
	it("reads an expired pause as one never set", () => {
		const now = (before: Record<string, unknown>) =>
			commandSpec("control.clear")?.changes(before, {}, "imports")[0].now;
		expect(now({ set: true, in_force: false, until: "2026-11-01T00:00:00+00:00" })).toBe(
			now({ set: false }),
		);
	});
});

describe("the status commands", () => {
	// What goes public is shown whole: the parts as the API stores them, a
	// list, beside the line the operator typed.
	it("reads the stored parts and the typed ones alike", () => {
		const rows = commandSpec("status.publish")?.changes(
			{ published: true, state: "degraded", message: "Slow.", affected: ["coach"] },
			{ state: "outage", message: "Down.", affected: "coach, api" },
			"public",
		);
		expect(rows?.[0].after).toContain("Down.");
		expect(rows?.[1]).toMatchObject({ now: "coach", after: "coach, api" });
	});

	// The act goes on top of the file the review showed: it names that
	// version, and the API refuses it if someone has posted since.
	it("carries the version its review read, and nothing else from it", () => {
		const spec = commandSpec("status.publish") as CommandSpec;
		const before = { generation: 7, state: "operational", published: true };
		expect(actArgs(spec, { state: "degraded", message: "Slow." }, before)).toEqual({
			state: "degraded",
			message: "Slow.",
			generation: 7,
		});
	});

	it("sends no version the review did not read, for the API to refuse", () => {
		const spec = commandSpec("status.clear") as CommandSpec;
		expect(actArgs(spec, {}, undefined)).toEqual({});
		expect(actArgs(spec, {}, { generation: null })).toEqual({});
	});

	it("carries nothing for a command that names nothing to carry", () => {
		const spec = commandSpec("account.set_limits") as CommandSpec;
		expect(actArgs(spec, { user_id: "u" }, { generation: 7 })).toEqual({ user_id: "u" });
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
		expect(start("device.revoke", "u1", "device_id=d1&reason=forged")).toEqual({ device_id: "d1" });
	});

	// A network's key may not be in a URL (shared/lib/handover.ts), so no
	// link can fill it, nor anything else in a slow-down.
	it("fills no network from a link", () => {
		const args = start("control.set", "signups", "network=k3y-0f-net&reason=forged&value=1");
		expect(args).toEqual({ until: "", reason: "", value: "" });
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

/**
 * The operator API's own schema for each command's arguments
 * (`x-command-args` in the generated openapi.json, which `pnpm
 * gen:types:check` keeps in step with the API). A key the model does not
 * have is dropped by pydantic without a word, and a box of the wrong kind is
 * refused only when the operator presses the button; both are a spec
 * disagreeing with the runner, and both show here.
 */
interface Schema {
	$ref?: string;
	type?: string;
	enum?: unknown[];
	anyOf?: Schema[];
	items?: Schema;
	properties?: Record<string, Schema>;
	required?: string[];
	minLength?: number;
	maxLength?: number;
	minimum?: number;
	format?: string;
}

const openapi = JSON.parse(
	readFileSync(new URL("../shared/api/openapi.json", import.meta.url), "utf8"),
) as { "x-command-args": Record<string, Schema>; components: { schemas: Record<string, Schema> } };

const resolve = (schema: Schema): Schema =>
	schema.$ref
		? resolve(openapi.components.schemas[schema.$ref.split("/").pop() ?? ""] ?? {})
		: schema;

/** Why `value` does not hold to `schema`, or null when it does: only the
 * keywords the argument models use. */
function problem(value: unknown, at: Schema): string | null {
	const schema = resolve(at);
	if (schema.anyOf) {
		return schema.anyOf.some((s) => problem(value, s) === null) ? null : "fits none of its shapes";
	}
	if (schema.enum && !schema.enum.includes(value)) return `${JSON.stringify(value)} is not offered`;
	if (schema.minimum !== undefined && typeof value === "number" && value < schema.minimum) {
		return "below its minimum";
	}
	switch (schema.type) {
		case "null":
			return value === null ? null : "not null";
		case "boolean":
			return typeof value === "boolean" ? null : "not a flag";
		case "integer":
			return Number.isInteger(value) ? null : "not a whole number";
		case "number":
			return typeof value === "number" ? null : "not a number";
		case "array":
			if (!Array.isArray(value)) return "not a list";
			return value.map((item) => problem(item, schema.items ?? {})).find(Boolean) ?? null;
		case "string":
			if (typeof value !== "string") return "not text";
			if (value.length < (schema.minLength ?? 0)) return "too short";
			if (value.length > (schema.maxLength ?? Number.POSITIVE_INFINITY)) return "too long";
			if (schema.format === "date" && !/^\d{4}-\d{2}-\d{2}$/.test(value)) return "not a day";
			if (schema.format === "date-time" && Number.isNaN(Date.parse(value))) return "not an instant";
			return null;
		default:
			return null;
	}
}

/** A box filled the way its argument takes it: one of its choices, a day or
 * an instant where it wants one, a number for a number box. */
function filled(field: CommandField, property: Schema | undefined): unknown {
	if (field.kind === "checkbox") return true;
	if (field.kind === "number") return "20";
	const shapes = property ? (resolve(property).anyOf ?? [resolve(property)]) : [];
	for (const shape of shapes) {
		const one = shape.type === "array" ? resolve(shape.items ?? {}) : shape;
		if (one.enum) return String(one.enum[0]);
		if (one.format === "date") return "2026-12-30";
		if (one.format === "date-time") return "2026-11-20T09:00:00Z";
	}
	return ID;
}

const ID = "6730f1a2b3c4d5e6f7a8b9c0";

/** The subjects a review of `spec` can be opened on. */
function subjectsOf(spec: CommandSpec, model: Schema): string[] {
	if (spec.subjectless) return ["x"];
	if (spec.family === "control") return (resolve(model).properties?.name?.enum ?? []).map(String);
	if (spec.family === "retention") return [EVERY_ORGANISATION, ID];
	return [ID];
}

describe("what a review sends, against the API's schema", () => {
	const commands = Object.entries(openapi["x-command-args"]);

	it("has a review for every command the API runs", () => {
		expect(commands.length).toBeGreaterThan(0);
		for (const [name] of commands) expect(commandSpec(name), name).toBeDefined();
	});

	it("sends, with every box filled, only arguments the command takes, each of its kind", () => {
		for (const [name, ref] of commands) {
			const spec = commandSpec(name);
			if (!spec) continue;
			const model = resolve(ref);
			for (const subject of subjectsOf(spec, model)) {
				const boxes = Object.fromEntries(
					fieldsOf(spec, subject).map((f) => [f.key, filled(f, model.properties?.[f.key])]),
				);
				const args = requestArgs(spec, subject, boxes);
				const wrong = [
					...(model.required ?? [])
						.filter((key) => !(key in args))
						.map((key) => `${key} is required and never sent`),
					...Object.entries(args).flatMap(([key, value]) => {
						const property = model.properties?.[key];
						if (!property) return [`${key} is not an argument, and would be dropped`];
						const why = problem(value, property);
						return why ? [`${key}: ${why}`] : [];
					}),
				];
				expect(wrong, `${name} on ${subject}`).toEqual([]);
			}
		}
	});

	// What an act carries from its review is what the preview answers, so it
	// must be an argument the command takes and one the preview can go
	// without.
	it("carries from the review only arguments the command takes, and none it requires", () => {
		for (const [name, ref] of commands) {
			const model = resolve(ref);
			for (const key of commandSpec(name)?.reviewed ?? []) {
				expect(model.properties?.[key], `${name} takes ${key}`).toBeDefined();
				expect(model.required ?? [], `${name} previews without ${key}`).not.toContain(key);
			}
		}
	});
});
