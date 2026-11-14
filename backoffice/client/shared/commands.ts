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

/** Which page a command belongs to, and how its subject is named. */
export interface Family {
	/** The argument the subject travels as. */
	subjectKey: "user_id" | "name" | "request_id";
	/** Where "back" goes, for a subject. */
	back: (subject: string) => { to: string; label: string };
	/** The confirmation field's label, when a command asks for one. */
	typedLabel: string;
	/** What the page says when `describe()` answers {exists: false}. */
	missing: string;
}

export const FAMILIES: Record<"account" | "control" | "erasure" | "deploy", Family> = {
	deploy: {
		// The subject is fixed ("api") and sent as nothing: both deploy
		// commands are subjectless on the wire.
		subjectKey: "name",
		back: () => ({ to: "/releases", label: "Back to releases" }),
		typedLabel: "Type it to confirm",
		missing: "There is nothing to act on.",
	},
	erasure: {
		subjectKey: "request_id",
		back: () => ({ to: "/compliance", label: "Back to privacy and compliance" }),
		typedLabel: "Type the reference to confirm",
		missing: "There is no open request with that id.",
	},
	account: {
		subjectKey: "user_id",
		back: (subject) => ({ to: `/accounts/${subject}`, label: "Back to the account" }),
		typedLabel: "Type the account's email to confirm",
		missing: "There is no account with that id.",
	},
	control: {
		subjectKey: "name",
		back: () => ({ to: "/access", label: "Back to access and controls" }),
		typedLabel: "Type the control's name to confirm",
		missing: "There is no control by that name.",
	},
};

export interface CommandSpec {
	name: string;
	family: keyof typeof FAMILIES;
	/** The command makes its subject rather than acting on one: the route's
	 * subject is a placeholder and is not sent. */
	subjectless?: boolean;
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
	/** Fixed, or by subject: a control's fields depend on which control. */
	fields?: CommandField[] | ((subject: string) => CommandField[]);
	/** The rows of the change table, from the subject's state and the
	 * arguments typed so far. */
	changes: (
		before: Record<string, unknown>,
		args: Record<string, unknown>,
		subject: string,
	) => Change[];
}

export const fieldsOf = (spec: CommandSpec, subject: string): CommandField[] =>
	typeof spec.fields === "function" ? spec.fields(subject) : (spec.fields ?? []);

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
		family: "account",
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
		family: "account",
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
		family: "account",
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
		family: "account",
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
		family: "account",
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
		family: "account",
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

/**
 * The platform's switches and limits (docs/backoffice.md § Controls). One
 * `control.set` serves every control, so what it asks for depends on which
 * one is the subject: a pause takes an end and a reason, a limit a value,
 * and sign-ups may take both, which slows them to a ceiling an hour.
 */
export const PAUSES = ["coach", "webhooks", "imports", "signups"] as const;
export const LIMITS = [
	"writes_per_minute_beats",
	"writes_per_minute_signals",
	"imports_per_hour",
] as const;
export type ControlName = (typeof PAUSES)[number] | (typeof LIMITS)[number];

export const isLimit = (name: string): boolean => (LIMITS as readonly string[]).includes(name);

/** A control, in the operator's words. */
export const CONTROLS: Record<ControlName, { title: string; note: string; unit?: string }> = {
	coach: { title: "Coach", note: "Paused stops every new coach request, for everyone." },
	webhooks: {
		title: "Webhook delivery",
		note: "Paused drops what would have been sent. There is no queue behind this, so nothing catches up when it comes back.",
	},
	imports: { title: "Imports", note: "Paused refuses new imports. Exports keep working." },
	signups: {
		title: "Sign-ups",
		note: "Paused refuses new accounts; a ceiling slows them to so many an hour. Nobody who has an account is kept out.",
	},
	writes_per_minute_beats: {
		title: "Beat writes per account",
		note: "Suggested: 120 a minute. A refusal asks the device to retry; check the request log before setting one lower.",
		unit: "a minute",
	},
	writes_per_minute_signals: {
		title: "Signal writes per account",
		note: "Suggested: 60 a minute.",
		unit: "a minute",
	},
	imports_per_hour: {
		title: "Imports per account",
		note: "Suggested: 10 an hour.",
		unit: "an hour",
	},
};

const PAUSE_FIELDS: CommandField[] = [
	{
		key: "until",
		label: "Until (UTC)",
		kind: "text",
		hint: "An instant like 2026-11-21T09:00:00Z. At most 7 days from now: every pause expires.",
	},
	{ key: "reason", label: "Reason, for your record", kind: "text", hint: "Never shown to users." },
];

const stateOf = (before: Record<string, unknown>, name: string): string => {
	if (!before.set || !before.in_force) return isLimit(name) ? "No limit" : "Running";
	if (name === "signups" && before.value) return `Slowed to ${before.value} an hour`;
	if (isLimit(name)) return `${before.value} ${CONTROLS[name as ControlName]?.unit ?? ""}`.trim();
	return `Paused until ${typeof before.until === "string" ? before.until.slice(0, 16) : "—"}`;
};

export const CONTROL_COMMANDS: CommandSpec[] = [
	{
		family: "control",
		name: "control.set",
		title: "Set it",
		action: "Set this control",
		about:
			"Takes effect for everyone within 30 seconds, on every instance. A pause has an end and lifts itself; a limit stays until it is cleared.",
		notices:
			"Everyone, at once: a paused request is refused with a fixed sentence (409, its own code). The reason stays here.",
		undo: "Yes. Clear it, or set it again. A pause also ends by itself.",
		fields: (name) =>
			isLimit(name)
				? [{ key: "value", label: CONTROLS[name as ControlName]?.unit ?? "Value", kind: "number" }]
				: name === "signups"
					? [
							...PAUSE_FIELDS,
							{
								key: "value",
								label: "Ceiling an hour",
								kind: "number",
								hint: "Leave empty to pause outright.",
							},
							{
								key: "network",
								label: "Network key",
								kind: "text",
								hint: "From the Trust page's signal, to slow that one network. Empty slows everyone. Ends at UTC midnight at the latest.",
							},
						]
					: PAUSE_FIELDS,
		changes: (before, args, name) => [
			{
				what: CONTROLS[name as ControlName]?.title ?? name,
				now: stateOf(before, name),
				after: isLimit(name)
					? args.value
						? `${args.value} ${CONTROLS[name as ControlName]?.unit ?? ""}`.trim()
						: "No limit"
					: name === "signups" && args.value
						? `${args.network ? "Network A slowed" : "Slowed"} to ${args.value} an hour until ${String(args.until ?? "—").slice(0, 16)}`
						: `Paused until ${String(args.until ?? "—").slice(0, 16)}`,
			},
		],
	},
	{
		family: "control",
		name: "control.clear",
		title: "Clear it",
		action: "Clear this control",
		about: "Puts it back to open: running, or no limit.",
		notices: "Everyone, within 30 seconds: whatever was refused is accepted again.",
		undo: "Yes. Set it again.",
		changes: (before, _args, name) => [
			{
				what: CONTROLS[name as ControlName]?.title ?? name,
				now: stateOf(before, name),
				after: isLimit(name) ? "No limit" : "Running",
			},
		],
	},
];

/**
 * The erasure request log (docs/backoffice.md § The pages, Compliance). A
 * request is logged with a reference the operator chooses — never an
 * address, which the API refuses — and closed with a reason once the
 * erasure ran, or there was no account, or they withdrew it.
 */
export const ERASURE_COMMANDS: CommandSpec[] = [
	{
		family: "erasure",
		subjectless: true,
		name: "erasure_request.log",
		title: "Log a request",
		action: "Log this request",
		about:
			"A request that arrived by mail gets a date here, so the deadline is visible before anything is queued. The account, if there is one, is named by its id; someone with no account is a reference alone.",
		notices: "Nobody. This is your own record; queueing the erasure is a separate act.",
		undo: "Close it with a reason. Nothing is deleted by logging.",
		fields: [
			{
				key: "reference",
				label: "Reference",
				kind: "text",
				hint: "Your own: a ticket number, the mail's date. Never an address.",
			},
			{ key: "received_on", label: "Received on (UTC day)", kind: "text", hint: "YYYY-MM-DD" },
			{
				key: "user_id",
				label: "Account id",
				kind: "text",
				hint: "Leave empty when there is no account.",
			},
		],
		changes: (before, args) => [
			{
				what: "The request",
				now: "Not logged",
				after: `Logged, received ${String(args.received_on || "—")}`,
			},
			{
				what: "Account",
				now: before.account === "exists" ? "Exists" : "None named",
				after: args.user_id ? "Named by id" : "None",
			},
		],
	},
	{
		family: "erasure",
		name: "erasure_request.close",
		title: "Close it",
		action: "Close this request",
		about:
			"Closes the request with a reason: erased (the job ran), no_account (nothing to erase), or withdrawn. A closed request is kept a year, then goes.",
		notices: "Nobody.",
		undo: "No; log it again if it was closed by mistake.",
		fields: [
			{
				key: "reason",
				label: "Reason",
				kind: "text",
				hint: "One of: erased, no_account, withdrawn",
			},
		],
		changes: (before, args) => [
			{
				what: "The request",
				now: `Open since ${String(before.received_on ?? "—")}`,
				after: args.reason ? `Closed: ${String(args.reason)}` : "Closed",
			},
		],
	},
];

/**
 * The deploy freeze (docs/backoffice.md § Deploy freeze): holds back the
 * API's builds until a time, and lifts it. The web app ships from its own
 * workflow and is not held — the review says so.
 */
export const DEPLOY_COMMANDS: CommandSpec[] = [
	{
		family: "deploy",
		subjectless: true,
		name: "deploy.freeze",
		title: "Freeze the API's deploys",
		action: "Freeze deploys",
		about:
			"Every API build that reaches its deploy step while this is in force skips its apply and goes red. It ends by itself at the time you set, within 7 days. The web app can still ship: it deploys from its own workflow, which this does not hold.",
		notices:
			"Whoever merges: their build goes red saying it was frozen. Users notice nothing — nothing changes for them.",
		undo: "Yes. Unfreeze it, then re-run the newest build: a build held back does not deploy by itself.",
		fields: [
			{
				key: "until",
				label: "Until (UTC)",
				kind: "text",
				hint: "An instant like 2026-11-15T09:00:00Z. At most 7 days from now.",
			},
			{ key: "reason", label: "Reason", kind: "text", hint: "Shown in the build's log." },
		],
		changes: (before, args) => [
			{
				what: "API deploys",
				now: before.frozen
					? `Frozen until ${String(before.until ?? "—").slice(0, 16)}`
					: "Shipping",
				after: `Frozen until ${String(args.until || "—").slice(0, 16)}`,
			},
			{ what: "Web app deploys", now: "Shipping", after: "Still shipping" },
		],
	},
	{
		family: "deploy",
		subjectless: true,
		name: "deploy.unfreeze",
		title: "Lift the freeze",
		action: "Lift the freeze",
		about:
			"API builds deploy again. One held back while frozen does not deploy by itself: re-run the newest build, which Releases names.",
		notices: "Nobody, until the next build deploys.",
		undo: "Yes. Freeze again.",
		changes: (before) => [
			{
				what: "API deploys",
				now: before.frozen
					? `Frozen until ${String(before.until ?? "—").slice(0, 16)}`
					: "Shipping",
				after: "Shipping",
			},
		],
	},
];

const EVERY_COMMAND = [
	...ACCOUNT_COMMANDS,
	...CONTROL_COMMANDS,
	...ERASURE_COMMANDS,
	...DEPLOY_COMMANDS,
];

export const commandSpec = (name: string): CommandSpec | undefined =>
	EVERY_COMMAND.find((c) => c.name === name);

/** The commands that share a subject with `spec`, for swapping one for
 * another. A subjectless command stands alone: nothing shares its subject. */
export const familyOf = (spec: CommandSpec): CommandSpec[] =>
	spec.subjectless
		? [spec]
		: EVERY_COMMAND.filter((c) => c.family === spec.family && !c.subjectless);

/** What every command puts on the record, said once. */
export const ON_THE_RECORD = "You, the command, the subject, and what it changed on either side.";

/** `webhooks_disabled` is a flag; the rest are numbers or text. */
export const emptyArgs = (spec: CommandSpec, subject: string): Record<string, unknown> =>
	Object.fromEntries(
		fieldsOf(spec, subject).map((f) => [f.key, f.kind === "checkbox" ? false : ""]),
	);
