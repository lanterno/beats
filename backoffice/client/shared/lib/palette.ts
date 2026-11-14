/**
 * The palette's rules, apart from its dialog so they can be tested.
 *
 * It goes to pages, opens a command's review, and finds one account by exact
 * address or id (docs/backoffice.md, stage 1). A command never runs from
 * it. Pages and commands are a short static list, so they are filtered by what
 * was typed; **people are not**: an account is found only by a whole address,
 * through the same POST the Accounts page makes, or by a whole id. A fragment
 * finds no one, and there is no "did you mean".
 */

import { ACCOUNT_COMMANDS } from "@/shared/commands";

const IDENTIFIER = /^[0-9a-f]{24}$/i;
/** Something@something.something with no spaces: the shape of a whole
 * address. The API still matches it exactly; this only decides whether to ask. */
const ADDRESS = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export type Intent =
	| { kind: "id"; id: string }
	| { kind: "address"; address: string }
	| { kind: "fragment"; text: string };

/** What the typed text can be used for. Only a whole id or a whole address
 * reaches an account; everything else only filters pages and commands. */
export function intentOf(typed: string): Intent {
	const text = typed.trim();
	if (IDENTIFIER.test(text)) return { kind: "id", id: text };
	if (ADDRESS.test(text)) return { kind: "address", address: text };
	return { kind: "fragment", text };
}

export interface Destination {
	label: string;
	to: string;
}

export const PAGES: Destination[] = [
	{ label: "Today", to: "/" },
	{ label: "Work queue", to: "/queue" },
	{ label: "Accounts", to: "/accounts" },
	{ label: "Organisations", to: "/organisations" },
	{ label: "Trust and safety", to: "/trust" },
	{ label: "Jobs and windows", to: "/jobs" },
	{ label: "Capacity and cost", to: "/capacity" },
	{ label: "Releases", to: "/releases" },
	{ label: "Privacy and compliance", to: "/compliance" },
	{ label: "Audit log", to: "/audit" },
	{ label: "Runbooks", to: "/runbooks" },
	{ label: "Access and controls", to: "/access" },
];

/** Pages whose name contains the typed text; every page for nothing typed. */
export function pagesFor(intent: Intent): Destination[] {
	if (intent.kind !== "fragment") return [];
	const needle = intent.text.toLowerCase();
	return PAGES.filter((page) => page.label.toLowerCase().includes(needle));
}

/**
 * A command's review, for an account named by its whole id. Every command
 * here acts on an account, so without an id there is nothing to review, and
 * the review page itself is the only place one can be carried out.
 */
export function reviewsFor(intent: Intent): Destination[] {
	if (intent.kind !== "id") return [];
	return [
		{ label: `Open account ${intent.id}`, to: `/accounts/${intent.id}` },
		...ACCOUNT_COMMANDS.map((spec) => ({
			label: `Review: ${spec.title}`,
			to: `/review/${spec.name}/${intent.id}`,
		})),
	];
}
