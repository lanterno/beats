/**
 * The queue's rules, apart from the page so they can be tested: which bucket a
 * row is in, how its due date reads, and what each kind of row says and
 * links to. The API answers ids and dates only (`GET /api/operator/queue`);
 * every word here is the control plane's own.
 */

import type { QueueRow } from "@/shared/api/schema";
import { CONTROLS, type ControlName } from "@/shared/commands";

export type Bucket = "overdue" | "today" | "later";

const DAY = 24 * 60 * 60 * 1000;

/**
 * A row with no stored date (an ownerless organisation, a coach cap in reach)
 * is due when it was read, so it is "today" rather than overdue: nothing says
 * how long it has been true. A dated row is overdue once its due instant has
 * passed, today if it falls before the next UTC midnight, and later after.
 */
export function bucketOf(row: Pick<QueueRow, "since" | "due">, now: Date): Bucket {
	if (!row.since) return "today";
	const due = Date.parse(row.due);
	if (due < now.getTime()) return "overdue";
	const midnight = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1);
	return due < midnight ? "today" : "later";
}

/** "Overdue 3 d", "Overdue 2 h", "Today", "5 days left". */
export function dueLabel(row: Pick<QueueRow, "since" | "due">, now: Date): string {
	const bucket = bucketOf(row, now);
	if (bucket === "today") return "Today";
	const gap = Math.abs(Date.parse(row.due) - now.getTime());
	if (bucket === "overdue") {
		return gap >= DAY
			? `Overdue ${Math.floor(gap / DAY)} d`
			: `Overdue ${Math.max(1, Math.floor(gap / (DAY / 24)))} h`;
	}
	const days = Math.ceil(gap / DAY);
	return days === 1 ? "1 day left" : `${days} days left`;
}

interface Kind {
	/** The row's sentence, given its subject and count. */
	title: (row: QueueRow) => string;
	/** The column under "Kind". */
	label: string;
	why: string;
	next: string;
	to: (row: QueueRow) => string;
	/** The runbook it fits, by id (shared/runbooks.ts). */
	runbook: string;
}

const short = (id: string) => id.slice(-6);

export const KINDS: Record<QueueRow["kind"], Kind> = {
	organisation_without_owner: {
		title: (row) => `Organisation ${short(row.subject_id)} has no owner`,
		label: "Organisation",
		why: "Nobody can manage its members or close it. You can step in only when the organisation asks.",
		next: "Open the organisation",
		to: (row) => `/organisations/${row.subject_id}`,
		runbook: "organisation-owner",
	},
	organisation_all_owners_suspended: {
		title: (row) => `Every owner of organisation ${short(row.subject_id)} is suspended`,
		label: "Organisation",
		why: "Its owners are there but cannot sign in, so in practice nobody manages it.",
		next: "Open the organisation",
		to: (row) => `/organisations/${row.subject_id}`,
		runbook: "organisation-owner",
	},
	job_failed: {
		title: (row) => `Job ${short(row.subject_id)} failed three times`,
		label: "Job",
		why: "It gave up after its third attempt and will not try again. Read its last error, then queue the command again or leave it.",
		next: "Open the job queue",
		to: () => "/jobs",
		runbook: "job-failed",
	},
	job_queued: {
		title: (row) => `Job ${short(row.subject_id)} is waiting out its window`,
		label: "Job",
		why: "It runs when its window ends. Until then it can still be cancelled, which is the reason the window exists.",
		next: "Open the job queue",
		to: () => "/jobs",
		runbook: "job-failed",
	},
	approvals_superseded: {
		title: (row) =>
			`${row.count === 1 ? "An approved month was" : `${row.count} approved months were`} superseded in organisation ${short(row.subject_id)}`,
		label: "Organisation",
		why: "A contract change moved figures inside an approved month. The organisation reopens it; this only says it has not, yet. No member is named here.",
		next: "Open the organisation",
		to: (row) => `/organisations/${row.subject_id}`,
		runbook: "organisation-waiting",
	},
	absence_requests_pending: {
		title: (row) =>
			`${row.count === 1 ? "An absence request is" : `${row.count} absence requests are`} waiting in organisation ${short(row.subject_id)}`,
		label: "Organisation",
		why: "Nobody there has decided them. Usually a decider is away; the organisation answers, not you. No member is named here.",
		next: "Open the organisation",
		to: (row) => `/organisations/${row.subject_id}`,
		runbook: "organisation-waiting",
	},
	control_paused: {
		title: (row) =>
			`${CONTROLS[row.subject_id as ControlName]?.title ?? row.subject_id} is paused for everyone`,
		label: "Control",
		why: "You, or another operator, paused it on purpose. It lifts itself at the instant shown; clear it sooner from access and controls.",
		next: "Open access and controls",
		to: () => "/access",
		runbook: "control-paused",
	},
	account_near_coach_cap: {
		title: (row) => `Account ${short(row.subject_id)} is at 80% of its coach cap`,
		label: "Cost",
		why: "The coach stops for them when they reach it, until the month turns. Decide whether that is what you want.",
		next: "Open the account",
		to: (row) => `/accounts/${row.subject_id}`,
		runbook: "coach-cap",
	},
};

const WORDS = ["Nothing is", "One thing is", "Two things are", "Three things are"];

/** The page's sentence: how many are waiting, and how many are overdue. */
export function queueHeadline(rows: QueueRow[], now: Date): string {
	const n = rows.length;
	const over = rows.filter((row) => bucketOf(row, now) === "overdue").length;
	const head = `${WORDS[n] ?? `${n} things are`} waiting.`;
	if (over === 0) return head;
	return `${head} ${over === 1 ? "One is" : `${over} are`} overdue.`;
}
