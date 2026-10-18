/**
 * Report Link Domain Types
 * A link a client opens their report with, no sign-in needed
 * (docs/billing.md, phase 1c): one client, some of its billed projects, a
 * stretch of finished days counted in one zone, what it shows, and the last
 * day it opens. Its token is shown once, when it is made, and is never part
 * of a `ReportLink`.
 */

export interface ReportLinkProject {
	id: string;
	/** The project's name today. */
	name: string;
}

export interface ReportLink {
	id: string;
	clientId: string;
	/** The maker's own name for it; the client never sees it. */
	label?: string;
	first: string; // YYYY-MM-DD
	last: string; // YYYY-MM-DD
	/** The IANA zone its days are counted in. */
	tz: string;
	showAmounts: boolean;
	showNotes: boolean;
	/**
	 * The projects it was made over that are still billed to its client. It
	 * only ever shrinks: one that left the client never comes back to it.
	 */
	projects: ReportLinkProject[];
	/** The last day it opens, in `tz`. */
	expiresOn: string;
	createdAt: string; // ISO datetime
	/** `ended` once `expiresOn` has passed in `tz`; an ended link stays listed until removed. */
	state: "live" | "ended";
}

/** What a report covers and shows: the preview's body. */
export interface ReportScopeInput {
	clientId: string;
	projectIds: string[];
	first: string;
	last: string;
	showAmounts: boolean;
	showNotes: boolean;
}

/** What a link is made of: the scope, the maker's label and its last day. */
export interface ReportLinkInput extends ReportScopeInput {
	label?: string;
	expiresOn: string;
}

/** A link just made, with its token: the only time the token is anywhere. */
export interface ReportLinkMade {
	link: ReportLink;
	token: string;
}
