/**
 * The runbooks: what to do when a queue row or an alert lands, as static
 * pages in the bundle (roadmaps/backoffice.md, stage 1). The alert runbooks
 * start from the `documentation` blocks in terraform/alerts.tf; a change to
 * one is made in both places, because the mail that pages the owner carries
 * that text and this page should not disagree with it.
 *
 * Each has a `reviewed_on`. After six months a runbook is marked stale: the
 * steps may still be right, but nobody has checked. Nothing records when one
 * was last *used* — that is a new record nobody has decided to keep.
 */

export interface Runbook {
	id: string;
	/** "When …" — the situation, as the operator meets it. */
	title: string;
	/** `YYYY-MM-DD`. */
	reviewed_on: string;
	/** What it is and why it matters, in a sentence or two. */
	about: string;
	steps: string[];
}

/** How long a runbook goes unreviewed before the page says so. */
export const STALE_AFTER_MONTHS = 6;

/** Whether `reviewed_on` is more than six calendar months before `today`. */
export function isStale(reviewedOn: string, today: Date): boolean {
	const [y, m, d] = reviewedOn.split("-").map(Number);
	if (!y || !m || !d) return true;
	const due = Date.UTC(y, m - 1 + STALE_AFTER_MONTHS, d);
	return today.getTime() >= due;
}

export const RUNBOOKS: Runbook[] = [
	{
		id: "job-failed",
		title: "A job failed",
		reviewed_on: "2026-11-14",
		about:
			"A queued command ran three times and failed each time. It will not try again: three attempts is terminal.",
		steps: [
			"Open Jobs and windows and read the job's last error. It is classified and cut to 500 characters; the full traceback is in the job runner's log at ERROR, which is also what paged you.",
			"Decide whether the command should still happen. Its rules are checked when it runs, so a deletion refused because the organisation gained an owner is the system working, not failing.",
			"If it should, fix the cause and queue the command again from its subject's page. There is no re-run: a new job starts a new window.",
		],
	},
	{
		id: "organisation-owner",
		title: "An organisation lost its owner",
		reviewed_on: "2026-11-14",
		about:
			"Nobody can manage its members, its projects or its closing. That includes every owner being suspended.",
		steps: [
			"Do nothing on your own initiative. You step in only when someone from the organisation asks, by mail you can point back to.",
			"Open the organisation and check who is still active, by role. Prefer handing ownership to an existing admin.",
			"If nobody is left to hand it to, the organisation can be closed, which gives each member their projects back.",
		],
	},
	{
		id: "coach-cap",
		title: "A coach cap is close",
		reviewed_on: "2026-11-14",
		about:
			"An account has spent 80% or more of its monthly coach budget. When it reaches it, the coach stops for them until the month turns.",
		steps: [
			"Open the account and look at its coach spend a day. A steady month that ran a little high is different from one day that ran away.",
			"If the cap is doing its job, leave it. If the account needs more, raise its limit with Set limits, and note why in your own records: the audit keeps the change, not the reason.",
		],
	},
	{
		id: "organisation-waiting",
		title: "An organisation is sitting on approvals or absence requests",
		reviewed_on: "2026-11-14",
		about:
			"An approved month was superseded by a contract change and never reopened, or absence requests have waited for a decision. Both are the organisation's to answer; the back office names no member.",
		steps: [
			"Open the organisation. Check that it still has people with a role that decides.",
			"If it does, this is theirs to work through, and the row leaves when they do. If it does not, it is the lost-owner runbook.",
		],
	},
	{
		id: "control-paused",
		title: "Something is paused for everyone",
		reviewed_on: "2026-11-14",
		about:
			"An operator threw one of the platform's switches: the coach, webhook delivery, imports or sign-ups. Users of that thing get a fixed 409 sentence; everything else works.",
		steps: [
			"Open access and controls and read who set it, when it ends and why. Every pause ends by itself within 7 days at most.",
			"If the incident is over, clear it: the public API notices within 30 seconds. If it is not, leave it, and set it again before it expires if it must outlast its end.",
			"Webhooks paused were dropped, not held: the WEBHOOKS_PAUSED_DROPPED lines in the API's log count what was lost.",
		],
	},
	{
		id: "erasure-request",
		title: "Someone asks for erasure",
		reviewed_on: "2026-11-14",
		about:
			"A request arrives by mail at the address in PRIVACY.md. The law gives one month from that day; the promise is deletion seven days after queueing.",
		steps: [
			"Log it on Privacy and compliance the day it arrives, with your own reference and the account's id. Never the address: the row outlives the account.",
			"Check the mail came from the address on the account. Find the account by that exact address, and compare.",
			"Queue the erasure from the account's page. Queueing suspends the account with wording that names the day the window ends, so an impersonated request can still be stopped by them.",
			"When the job has run, close the request as erased. If there was no account, close it as no_account; if they changed their mind inside the window, cancel the job and close it as withdrawn.",
		],
	},
	{
		id: "bad-release",
		title: "A release is bad",
		reviewed_on: "2026-11-14",
		about:
			"Something broke right after a deploy. A build never rolls back: deploy_lock.sh skips a commit the live one already contains, so re-running an older build does nothing.",
		steps: [
			"Revert the change on main. The revert is a new commit, so it deploys like any other.",
			"Watch the Cloud Build run through its terraform apply, then the uptime checks and the 5xx share.",
			"The web app ships separately, from the deploy job in .github/workflows/ui.yml: a bad SPA is reverted the same way, and its revert ships on its own.",
		],
	},
	{
		id: "uptime",
		title: "An uptime check is failing",
		reviewed_on: "2026-11-14",
		about:
			"An uptime check on the API's /health or the web app's / is failing from more than one probe location.",
		steps: [
			"The failed checks are in Logging with their reason: DNS, TLS, timeout, status or content.",
			"/health does not touch MongoDB: if it passes while the app fails, look at the database.",
		],
	},
	{
		id: "api-5xx",
		title: "The API is answering 5xx",
		reviewed_on: "2026-11-14",
		about: "More than 2% of the API's requests over five minutes were answered with a 5xx.",
		steps: [
			"The request log has each one (httpRequest.status>=500), and the API's own log lines beside it carry the traceback.",
			"If it started with a deploy, it is the bad-release runbook.",
		],
	},
	{
		id: "api-latency",
		title: "The API is slow",
		reviewed_on: "2026-11-14",
		about: "The API's p95 latency has been above 5 s for ten minutes.",
		steps: [
			"The dashboard shows whether instances are at their maximum or starting cold; a cold start takes about 30 s.",
			'The request log, filtered on httpRequest.latency>"5s", shows which routes.',
		],
	},
	{
		id: "api-instances",
		title: "The API is at its maximum instances",
		reviewed_on: "2026-11-14",
		about: "Every instance the API may run has been busy for ten minutes.",
		steps: [
			"Slow requests hold instances: look at the latency chart first.",
			"If traffic has simply grown, raise max_instances in the tfvars.",
		],
	},
	{
		id: "public-route-failures",
		title: "A public route is failing",
		reviewed_on: "2026-11-14",
		about:
			"A public route has failed more than 20 times in ten minutes; the incident names the route.",
		steps: [
			"Query the request log for that route and group by httpRequest.remoteIp to see who is behind it.",
		],
	},
	{
		id: "api-rejections",
		title: "Rejections are spiking",
		reviewed_on: "2026-11-14",
		about: "The API has turned away more than 200 requests under /api/ in ten minutes.",
		steps: [
			"The dashboard splits them by status.",
			"The request log, grouped by httpRequest.remoteIp and httpRequest.userAgent, shows whether it is one client retrying or many addresses.",
		],
	},
];

export const runbook = (id: string): Runbook | undefined => RUNBOOKS.find((r) => r.id === id);
