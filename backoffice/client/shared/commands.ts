/**
 * What each command is, in the operator's words.
 *
 * The API answers what a command *would* change (`describe()`, through the
 * preview). It cannot answer who notices or whether the act can be taken
 * back without running it, so those are fixed text per command, written here
 * (docs/backoffice.md § The pages — "Who notices" and "Can you undo it" are
 * fixed text per command).
 *
 * This is copy, not rules. A guard written here would be a second opinion
 * about what the runner allows, and the runner's is the only one: every
 * entry's `name` is a command the API already refuses or performs on its own
 * terms, and nothing here decides anything.
 */

import { APP_NAME } from "@/shared/config/brand";

/** A field beyond the subject, for the command's own arguments. */
export interface CommandField {
	key: string;
	label: string;
	kind: "text" | "number" | "checkbox";
	/** Said under the field, where the label is not enough. */
	hint?: string;
	/** A page may hand this box its value in the link it opens the review
	 * with (`startingArgs`). Only for what names the thing acted on — a
	 * device — never for what is said or decided: a link anyone can craft
	 * must not open a status post already written. A network's key is no
	 * box at all: it may not be in a link (shared/lib/handover.ts). */
	linked?: true;
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
	/** The arguments the subject travels as: one, or none for a subject
	 * that is the whole platform (a purge of `all`). */
	named: (subject: string) => Record<string, unknown>;
	/** Where "back" goes, for a subject. */
	back: (subject: string) => { to: string; label: string };
	/** The confirmation field's label, when a command asks for one. */
	typedLabel: (subject: string) => string;
	/** What the page says when `describe()` answers {exists: false}. */
	missing: string;
}

/** The subject as one argument. */
const as =
	(key: string) =>
	(subject: string): Record<string, unknown> => ({ [key]: subject });
const nothing = () => ({});
const typeIt = () => "Type it to confirm";
/** The platform-wide purge's subject, typed back to confirm it. */
export const EVERY_ORGANISATION = "all";

export const FAMILIES: Record<
	| "account"
	| "device"
	| "control"
	| "erasure"
	| "deploy"
	| "status"
	| "organisation"
	| "retention"
	| "job",
	Family
> = {
	status: {
		named: nothing,
		back: () => ({ to: "/", label: "Back to Today" }),
		typedLabel: typeIt,
		missing: "There is nothing to act on.",
	},
	deploy: {
		// The subject is fixed ("api") and sent as nothing: both deploy
		// commands are subjectless on the wire.
		named: nothing,
		back: () => ({ to: "/releases", label: "Back to releases" }),
		typedLabel: typeIt,
		missing: "There is nothing to act on.",
	},
	erasure: {
		named: as("request_id"),
		back: () => ({ to: "/compliance", label: "Back to privacy and compliance" }),
		typedLabel: () => "Type the reference to confirm",
		missing: "There is no open request with that id.",
	},
	account: {
		named: as("user_id"),
		back: (subject) => ({ to: `/accounts/${subject}`, label: "Back to the account" }),
		typedLabel: () => "Type the account's email to confirm",
		missing: "There is no account with that id.",
	},
	// The account is the subject; which of its devices is the one field.
	device: {
		named: as("user_id"),
		back: (subject) => ({ to: `/accounts/${subject}`, label: "Back to the account" }),
		typedLabel: typeIt,
		missing: "There is no account with that id.",
	},
	control: {
		named: as("name"),
		back: () => ({ to: "/access", label: "Back to access and controls" }),
		typedLabel: () => "Type the control's name to confirm",
		missing: "There is no control by that name.",
	},
	organisation: {
		named: as("organisation_id"),
		back: (subject) => ({ to: `/organisations/${subject}`, label: "Back to the organisation" }),
		typedLabel: () => "Type the organisation's name to confirm",
		missing: "There is no organisation with that id.",
	},
	// One organisation, from its page, or every one, from compliance.
	retention: {
		named: (subject) => (subject === EVERY_ORGANISATION ? {} : { organisation_id: subject }),
		back: (subject) =>
			subject === EVERY_ORGANISATION
				? { to: "/compliance", label: "Back to privacy and compliance" }
				: { to: `/organisations/${subject}`, label: "Back to the organisation" },
		typedLabel: (subject) =>
			subject === EVERY_ORGANISATION
				? `Type ${EVERY_ORGANISATION} to confirm`
				: "Type the organisation's name to confirm",
		missing: "There is no organisation with that id.",
	},
	job: {
		named: as("job_id"),
		back: () => ({ to: "/jobs", label: "Back to jobs and windows" }),
		typedLabel: typeIt,
		missing: "There is no job with that id.",
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

/** A count from the preview, or a dash before it has one. */
const count = (value: unknown): string => (typeof value === "number" ? String(value) : "—");
/** An instant from the preview, to the minute. */
const instant = (value: unknown): string =>
	typeof value === "string" && value ? value.slice(0, 16).replace("T", " ") : "—";
const capital = (word: string): string => word.charAt(0).toUpperCase() + word.slice(1);

/** One device of an account, named by its id: the account page links each
 * device's own review, so the id is handed over in the link. */
export const DEVICE_COMMANDS: CommandSpec[] = [
	{
		family: "device",
		name: "device.revoke",
		title: "Revoke a device",
		action: "Revoke this device",
		about:
			"This one device stops working and has to be paired again. The account's other devices, its sessions and its passkeys are untouched.",
		notices:
			"They do, when the device next reaches the API, within 30 seconds: it asks to be paired again.",
		undo: "Not as such, but they can pair it again in a minute.",
		fields: [
			{
				key: "device_id",
				label: "Device id",
				kind: "text",
				hint: "From the account's list of devices.",
				linked: true,
			},
		],
		changes: (before) => [
			{
				what: "The device",
				now:
					before.revoked === true
						? "Revoked"
						: before.revoked === false
							? "Paired"
							: "Not one of this account's",
				after: "Revoked",
			},
		],
	},
];

/**
 * What the operator may do for an organisation with no owner, and only
 * when someone there asked (docs/backoffice.md § The operator's
 * organisation acts). Each is refused with ORGANISATION_HAS_OWNER the moment
 * an owner exists, a suspended one included; nothing here checks that.
 */
export const ORGANISATION_COMMANDS: CommandSpec[] = [
	{
		family: "organisation",
		name: "organisation.grant_owner",
		title: "Make the requester owner",
		action: "Make them owner",
		about:
			"Gives the owner role to the member who asked, by mail from the address on their account. Nobody else can be given it, and only if no active member outranks them. Once it has an owner, nothing here can act on the organisation again.",
		notices: `The requester, who can run it again, and its admins, in its audit log, where it reads as done by ${APP_NAME} — never by you.`,
		undo: "Not from here. The new owner can hand the role on.",
		fields: [
			{
				key: "user_id",
				label: "The requester's account id",
				kind: "text",
				hint: "Find their account by the address the mail came from, and copy its id.",
			},
		],
		changes: (before) => [
			{
				what: "Owners",
				now: before.owners === 0 ? "None" : count(before.owners),
				after: "The requester",
			},
			{
				what: "The requester's role",
				now:
					typeof before.requester_role === "string"
						? capital(before.requester_role)
						: "Not an active member",
				after: "Owner",
			},
			{
				what: "The highest role held",
				now: typeof before.highest_role === "string" ? capital(before.highest_role) : "Nobody",
				after: "Owner",
			},
		],
	},
	{
		family: "organisation",
		name: "organisation.begin_closing",
		title: "Start or move the closing",
		action: "Set the closing day",
		about:
			"Gives every member notice that the organisation closes, so each can take their projects with them first. At least 30 days out, or any day later than a notice already running.",
		notices: "Every member: the organisation shows the day it closes.",
		undo: "Yes, until that day: cancel the closing.",
		fields: [
			{
				key: "closes_on",
				label: "Closes on",
				kind: "text",
				hint: "YYYY-MM-DD. Empty: 60 days from today, in the organisation's timezone.",
			},
		],
		changes: (before, args) => [
			{
				what: "Closing",
				now: typeof before.closes_on === "string" ? `On ${before.closes_on}` : "Not closing",
				after: args.closes_on ? `On ${String(args.closes_on)}` : "60 days from today",
			},
		],
	},
	{
		family: "organisation",
		name: "organisation.cancel_closing",
		title: "Cancel the closing",
		action: "Cancel the closing",
		about: "Withdraws the notice. The organisation stays as it is.",
		notices: "Every member: the closing day goes.",
		undo: "Yes. Start closing again, with a fresh notice of at least 30 days.",
		changes: (before) => [
			{
				what: "Closing",
				now: typeof before.closes_on === "string" ? `On ${before.closes_on}` : "Not closing",
				after: "Not closing",
			},
		],
	},
	{
		family: "organisation",
		name: "organisation.delete",
		title: "Delete the organisation",
		action: "Queue the deletion",
		about:
			"Once its closing day has passed: each member is handed a personal copy of every project they hold rows or a contract on, then the organisation goes, with its projects, memberships, timesheets and audit log. It waits a day first, and is refused when it runs if the day has not come or it has an owner again.",
		notices:
			"Every member: it leaves their list, and its projects come back as their own. Its admins lose its audit log with it.",
		undo: "Yes, until it runs a day from now: cancel it on Jobs and windows. After that, never.",
		grave: true,
		changes: (before) => [
			{
				what: "Closing day",
				now: typeof before.closes_on === "string" ? before.closes_on : "Not closing",
				after: "Deleted when it runs",
			},
			{
				what: "Projects",
				now: count(before.projects),
				after: "Handed back to whoever holds rows on them",
			},
			{ what: "Active members", now: count(before.members), after: "None" },
			{
				what: "Its audit log",
				now: "Kept",
				after: "Deleted. This back office's record of the act stays",
			},
		],
	},
];

/**
 * The retention purge (decision 30 in docs/organisations.md): never
 * scheduled, because PRIVACY.md and the DPA promise an operator runs it.
 * One organisation from its page, or every one from compliance.
 */
export const RETENTION_COMMANDS: CommandSpec[] = [
	{
		family: "retention",
		name: "retention.purge",
		title: "Purge records past their period",
		action: "Queue the purge",
		about:
			"Rows past their organisation's retention period: a former member's go, a current member's lose the organisation's stamp and stay theirs, and expired timesheets, decided requests and audit events go. Across every organisation, this back office's own audit past four years goes too. It waits a day first.",
		notices: "Nobody is told. Each organisation's admins see one line in its audit log.",
		undo: "Yes, until it runs a day from now: cancel it on Jobs and windows. After that, what went is gone.",
		grave: true,
		changes: (before) => [
			{
				what: "Organisations",
				now: `${count(before.would_touch_organisations)} with rows past their period`,
				after: before.would_touch_organisations === 0 ? "Nothing to purge" : "Purged when it runs",
			},
			{
				what:
					typeof before.cutoff === "string"
						? `Rows dated before ${before.cutoff}`
						: "Rows past their period",
				now: `${count(before.rows_deleted)} kept`,
				after: "Deleted",
			},
			{
				what: "Current members' rows past it",
				now: `${count(before.rows_unstamped)} on the record`,
				after: "Theirs, off the record",
			},
		],
	},
];

/** A queued job's second thoughts (docs/backoffice.md § Jobs). */
export const JOB_COMMANDS: CommandSpec[] = [
	{
		family: "job",
		name: "job.cancel",
		title: "Cancel this job",
		action: "Cancel the job",
		about:
			"Stops a queued command before its window ends. Cancelling an erasure also lifts the suspension queueing it put on the account, and never a suspension for anything else.",
		notices: "Whoever it was for, if it was an erasure: they can sign in again.",
		undo: "Queue the command again. It waits a new window.",
		changes: (before) => [
			{
				what: typeof before.command === "string" ? before.command : "The job",
				now:
					before.state === "queued"
						? `Waiting, runs from ${instant(before.run_after)} UTC`
						: capital(String(before.state ?? "—")),
				after: "Cancelled",
			},
			{
				what: "Its subject",
				now: typeof before.subject_id === "string" ? before.subject_id : "—",
				after: "Untouched, but for an erasure's own suspension",
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

/** A control, in the operator's words. `plural` is for the verb a sentence
 * gives its title: "Imports are paused", "Coach is paused". */
export const CONTROLS: Record<
	ControlName,
	{ title: string; note: string; unit?: string; plural?: boolean }
> = {
	coach: { title: "Coach", note: "Paused stops every new coach request, for everyone." },
	webhooks: {
		title: "Webhook delivery",
		note: "Paused drops what would have been sent. There is no queue behind this, so nothing catches up when it comes back.",
	},
	imports: {
		title: "Imports",
		note: "Paused refuses new imports. Exports keep working.",
		plural: true,
	},
	signups: {
		title: "Sign-ups",
		note: "Paused refuses new accounts; a ceiling slows them to so many an hour. Nobody who has an account is kept out.",
		plural: true,
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
	if (!before.set || !before.in_force)
		return isLimit(name) ? "No limit" : before.one_network ? "Not slowed" : "Running";
	if (name === "signups" && before.value) return `Slowed to ${before.value} an hour`;
	if (isLimit(name)) return `${before.value} ${CONTROLS[name as ControlName]?.unit ?? ""}`.trim();
	return `Paused until ${typeof before.until === "string" ? before.until.slice(0, 16) : "—"}`;
};

/** The row's subject. Sign-ups say whom they cover: everyone, or the one
 * network a page handed over (shared/lib/handover.ts), which is named and
 * never shown by its key. */
const controlWhat = (name: string, args: Record<string, unknown>): string =>
	args.network
		? "Sign-ups from one network"
		: name === "signups"
			? "Sign-ups, for everyone"
			: (CONTROLS[name as ControlName]?.title ?? name);

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
								hint: "Leave empty to pause outright. One network is only ever slowed, until UTC midnight at the latest.",
							},
						]
					: PAUSE_FIELDS,
		changes: (before, args, name) => [
			{
				what: controlWhat(name, args),
				now: stateOf(before, name),
				after: isLimit(name)
					? args.value
						? `${args.value} ${CONTROLS[name as ControlName]?.unit ?? ""}`.trim()
						: "No limit"
					: name === "signups" && args.value
						? `Slowed to ${args.value} an hour until ${String(args.until ?? "—").slice(0, 16)}`
						: args.network
							? "Slowed, once a ceiling is written"
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
		changes: (before, args, name) => [
			{
				what: controlWhat(name, args),
				now: stateOf(before, name),
				after: isLimit(name) ? "No limit" : args.network ? "Not slowed" : "Running",
			},
		],
	},
];

/**
 * The erasure request log (docs/backoffice.md § The pages, Compliance). A
 * request is logged with a reference the operator chooses — a ticket number
 * or the mail's date, which is all the API takes, so never a name or an
 * address. The account's erasure closes it as erased when it runs; the rest
 * are closed by hand, when there was no account or they withdrew it.
 */
export const ERASURE_COMMANDS: CommandSpec[] = [
	{
		family: "erasure",
		subjectless: true,
		name: "erasure_request.log",
		title: "Log a request",
		action: "Log this request",
		about:
			"A request that arrived by mail gets a date here, so the deadline is visible before anything is queued. The account, if there is one, is named by its id, and its erasure closes the request when it runs; someone with no account is a reference alone.",
		notices: "Nobody. This is your own record; queueing the erasure is a separate act.",
		undo: "Close it with a reason. Nothing is deleted by logging.",
		fields: [
			{
				key: "reference",
				label: "Reference",
				kind: "text",
				hint: "A ticket number or the mail's date, like T-1234 or 2026-11-14: a few letters at most, then digits. Never a name or an address.",
			},
			{ key: "received_on", label: "Received on (UTC day)", kind: "text", hint: "YYYY-MM-DD" },
			{
				key: "user_id",
				label: "Account id",
				kind: "text",
				hint: "The whole id, from the account's page. Leave empty when there is no account.",
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
			"Closes the request with a reason: erased, no_account (nothing to erase), or withdrawn. An erasure closes the requests naming its account by itself; erased by hand is for the rest. A closed request is kept a year, then goes.",
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

/**
 * Telling customers what is happening (docs/status-page.md): one public file,
 * written whole. The review shows exactly what will go public before it
 * does. Nothing about a person in a post: the file is public and keeps its
 * history.
 */
export const STATUS_STATES = ["degraded", "outage", "maintenance", "operational"] as const;
export const STATUS_PARTS = [
	"web app",
	"api",
	"sign-in",
	"coach",
	"integrations",
	"phone apps",
] as const;

export const STATUS_COMMANDS: CommandSpec[] = [
	{
		family: "status",
		subjectless: true,
		name: "status.publish",
		title: "Publish an update",
		action: "Publish this, publicly",
		about:
			"Goes to the public status page and the banner in the app within about a minute, for everyone. Name no account, organisation, id, count of people affected or internal hostname: the file is public and its history is kept.",
		notices: "Everyone who opens the app or the status page, within about a minute.",
		undo: "Post again. Nothing is deleted: the last twenty posts stay on the page.",
		fields: [
			{ key: "state", label: "State", kind: "text", hint: `One of: ${STATUS_STATES.join(", ")}` },
			{
				key: "message",
				label: "Message",
				kind: "text",
				hint: "At most 280 characters. Plain words.",
			},
			{
				key: "affected",
				label: "Affected",
				kind: "text",
				hint: `Comma-separated, from: ${STATUS_PARTS.join(", ")}. Empty for none.`,
			},
		],
		changes: (before, args) => [
			{
				what: "What customers see",
				now: before.published
					? `${before.state}${before.message ? `: ${before.message}` : ""}`
					: "Nothing published yet",
				after: `${String(args.state || "—")}: ${String(args.message || "—")}`,
			},
			{
				what: "Affected",
				now:
					Array.isArray(before.affected) && before.affected.length
						? before.affected.join(", ")
						: "—",
				after: String(args.affected || "—"),
			},
		],
	},
	{
		family: "status",
		subjectless: true,
		name: "status.clear",
		title: "Say it is over",
		action: "Publish the all-clear",
		about: "Posts operational, with a short message, so the page says when it ended.",
		notices: "Everyone, within about a minute: the banner goes.",
		undo: "Publish an update again.",
		fields: [
			{
				key: "message",
				label: "Message",
				kind: "text",
				hint: "Empty says: Everything is working again.",
			},
		],
		changes: (before, args) => [
			{
				what: "What customers see",
				now: before.published ? String(before.state) : "Nothing published yet",
				after: `operational: ${String(args.message || "Everything is working again.")}`,
			},
		],
	},
];

const EVERY_COMMAND = [
	...ACCOUNT_COMMANDS,
	...DEVICE_COMMANDS,
	...ORGANISATION_COMMANDS,
	...RETENTION_COMMANDS,
	...JOB_COMMANDS,
	...CONTROL_COMMANDS,
	...ERASURE_COMMANDS,
	...DEPLOY_COMMANDS,
	...STATUS_COMMANDS,
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

/**
 * The form a review opens with: every box empty but the ones a page may
 * hand over (`linked`), each read through `given` — the link's query today;
 * whatever carries it, nothing else is read.
 */
export function startingArgs(
	spec: CommandSpec,
	subject: string,
	given: (key: string) => string | null,
): Record<string, unknown> {
	const args = emptyArgs(spec, subject);
	for (const field of fieldsOf(spec, subject)) {
		const value = field.linked && field.kind !== "checkbox" ? given(field.key) : null;
		if (value !== null) args[field.key] = value;
	}
	return args;
}
