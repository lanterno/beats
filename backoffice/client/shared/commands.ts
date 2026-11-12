/**
 * What each command is, in the operator's words.
 *
 * The API answers what a command *would* change (`describe()`, through the
 * preview). It cannot answer who notices or whether the act can be taken
 * back without running it, so those are fixed text per command, written here
 * (roadmaps/backoffice.md, stage 1 — "Who notices" and "Can you undo it" are
 * fixed text per command).
 *
 * This is copy, not rules. A guard written here would be a second opinion
 * about what the runner allows, and the runner's is the only one: every
 * entry's `name` is a command the API already refuses or performs on its own
 * terms, and nothing here decides anything.
 */

/** A field beyond the subject, for the command's own arguments. */
export interface CommandField {
	key: string;
	label: string;
	kind: "text" | "number" | "checkbox";
	/** Said under the field, where the label is not enough. */
	hint?: string;
}

/** One row of "what will change". */
export interface Change {
	what: string;
	/** As it stands, read off the preview's `before`. */
	now: string;
	/** What this command promises to make it. */
	after: string;
}

export interface CommandSpec {
	name: string;
	/** What the operator calls it. */
	title: string;
	/** The button: a verb and its object. */
	action: string;
	/** What it does, in a sentence the operator reads before deciding. */
	about: string;
	/** Who, outside this office, notices. */
	notices: string;
	/** Whether it can be taken back. */
	undo: string;
	/** Destructive: the review wears the warning, and the button does not
	 * wear the sun. */
	grave?: boolean;
	fields?: CommandField[];
	/** The rows of the change table, from the subject's state and the
	 * arguments typed so far. */
	changes: (before: Record<string, unknown>, args: Record<string, unknown>) => Change[];
}

const limitRow = (
	what: string,
	before: Record<string, unknown>,
	args: Record<string, unknown>,
	key: string,
	unit: string,
): Change => {
	const now = before[key];
	const next = args[key];
	return {
		what,
		now: now === undefined || now === null ? "Platform default" : `${now} ${unit}`,
		after:
			next === undefined || next === null || next === "" ? "Platform default" : `${next} ${unit}`,
	};
};

/**
 * The account acts. Keyed by the command's own name, so a page can offer a
 * subset without restating any of this.
 */
export const ACCOUNT_COMMANDS: CommandSpec[] = [
	{
		name: "account.set_limits",
		title: "Set limits on writes or webhooks",
		action: "Save these limits",
		about:
			"Replaces this account's limits with what you type. An empty box means the platform's default, and the whole set is written at once.",
		notices:
			"They do, once a write is refused: the API answers 429 and the app retries. Nothing tells them a limit was set.",
		undo: "Yes. Clear limits puts every one of them back to the default.",
		fields: [
			{ key: "coach_monthly_budget_usd", label: "Coach $ a month", kind: "number" },
			{ key: "writes_per_minute_beats", label: "Beat writes a minute", kind: "number" },
			{ key: "writes_per_minute_signals", label: "Signal writes a minute", kind: "number" },
			{ key: "imports_per_hour", label: "Imports an hour", kind: "number" },
			{
				key: "webhooks_disabled",
				label: "Webhooks off",
				kind: "checkbox",
				hint: "Off drops what would have been sent: there is no queue behind it.",
			},
		],
		changes: (before, args) => [
			limitRow("Coach budget", before, args, "coach_monthly_budget_usd", "a month"),
			limitRow("Beat writes", before, args, "writes_per_minute_beats", "a minute"),
			limitRow("Signal writes", before, args, "writes_per_minute_signals", "a minute"),
			limitRow("Imports", before, args, "imports_per_hour", "an hour"),
			{
				what: "Webhooks",
				now: before.webhooks_disabled ? "Off" : "On",
				after: args.webhooks_disabled ? "Off" : "On",
			},
		],
	},
	{
		name: "account.clear_limits",
		title: "Clear limits",
		action: "Clear all limits",
		about: "Puts every limit on this account back to the platform's default.",
		notices: "They do, if a limit was refusing their writes: it stops refusing them.",
		undo: "Yes. Set them again.",
		changes: (before) => [
			{
				what: "Limits",
				now: before.overridden ? "Overridden" : "Platform default",
				after: "Platform default",
			},
		],
	},
	{
		name: "account.sign_out_everywhere",
		title: "Sign out everywhere",
		action: "Sign this account out",
		about:
			"Every session this account has open stops working. Their passkeys and devices are untouched, so they can sign in again straight away.",
		notices: "They do, on every device, at the next request. They can sign in again at once.",
		undo: "Nothing to undo: they simply sign in again.",
		changes: (before) => [
			{
				what: "Sessions open now",
				now:
					typeof before.sessions_valid_after === "string"
						? `Valid after ${before.sessions_valid_after.slice(0, 10)}`
						: "All valid",
				after: "All stop working",
			},
			{ what: "Passkeys and devices", now: "Unchanged", after: "Unchanged" },
		],
	},
	{
		name: "account.suspend",
		title: "Suspend for abuse",
		action: "Suspend this account",
		about:
			"They cannot sign in, and every open session stops. Nothing they have is deleted. The reason is for your own record and is never shown to them.",
		notices: "They do, the moment they next open the app. They are not told why.",
		undo: "Yes. Unsuspend puts it back, unless an erasure is queued.",
		grave: true,
		fields: [
			{
				key: "reason",
				label: "Reason, for your record",
				kind: "text",
				hint: "Kept in the audit, never shown to them.",
			},
		],
		changes: (before) => [
			{ what: "State", now: before.suspended ? "Suspended" : "Active", after: "Suspended" },
			{ what: "Sessions", now: "Working", after: "All stop working" },
			{ what: "What they have", now: "Kept", after: "Kept, untouched" },
		],
	},
	{
		name: "account.unsuspend",
		title: "Unsuspend",
		action: "Unsuspend this account",
		about:
			"They can sign in again. Refused while an erasure is queued — cancel the erasure instead, which lifts its suspension itself.",
		notices: "They do, the next time they try to sign in.",
		undo: "Yes. Suspend again.",
		changes: (before) => [
			{
				what: "State",
				now: before.suspended
					? `Suspended${before.suspended_kind ? ` for ${before.suspended_kind}` : ""}`
					: "Active",
				after: "Active",
			},
		],
	},
	{
		name: "account.erase",
		title: "Erase this account",
		action: "Queue this erasure",
		about:
			"Deletes everything they have, after a window in which you can still stop it, and only when they asked for it themselves from the address on the account.",
		notices:
			"They do, at once: queueing suspends the account with wording that names the day the window ends, so an impersonated request can still be stopped by them.",
		undo: "Yes, until the job runs. After that, never.",
		grave: true,
		changes: (before) => [
			{
				what: "State",
				now: before.suspended ? "Suspended" : "Active",
				after: "Suspended, with the erasure's wording",
			},
			{ what: "Projects, sessions, coach, devices", now: "Kept", after: "Deleted when it runs" },
			{ what: "Hours on an organisation's projects", now: "Kept", after: "Kept under a tombstone" },
			{
				what: "This back office's audit",
				now: "Holds the id",
				after: "Keeps the id, never an address",
			},
		],
	},
];

export const commandSpec = (name: string): CommandSpec | undefined =>
	ACCOUNT_COMMANDS.find((c) => c.name === name);

/** What every command puts on the record, said once. */
export const ON_THE_RECORD = "You, the command, the subject, and what it changed on either side.";

/** `webhooks_disabled` is a flag; the rest are numbers or text. */
export const emptyArgs = (spec: CommandSpec): Record<string, unknown> =>
	Object.fromEntries((spec.fields ?? []).map((f) => [f.key, f.kind === "checkbox" ? false : ""]));
