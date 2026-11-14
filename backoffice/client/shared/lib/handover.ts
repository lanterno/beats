/**
 * Handing an argument to the review page without putting it in a URL
 * (docs/backoffice.md § Trust). The network key a sign-up slow-down covers is
 * a hash of where people sign up from, and a URL is written down: in the
 * browser's history, in the request log of whatever serves the page when it
 * is opened afresh. The key travels in navigation state instead, and the URL
 * names only what was handed over (`?carried=network`), never its value, so
 * the review can tell when it arrived without it (a new tab, a copied link)
 * rather than read the absence as "everyone".
 */

/** A link to `pathname` carrying `carried` in navigation state: spread it into a `<Link>`. */
export function handOver(
	pathname: string,
	carried: Record<string, string>,
): { to: { pathname: string; search: string }; state: { carried: Record<string, string> } } {
	const search = new URLSearchParams();
	for (const key of Object.keys(carried)) search.append("carried", key);
	return { to: { pathname, search: `?${search}` }, state: { carried } };
}

/** What a page was handed: the arguments the URL names, read from navigation
 * state, and nothing the URL does not name. Null when one it names did not
 * arrive, so the page stops rather than act without it. */
export function handedOver(search: URLSearchParams, state: unknown): Record<string, string> | null {
	const given = (state as { carried?: Record<string, unknown> } | null)?.carried ?? {};
	const out: Record<string, string> = {};
	for (const key of search.getAll("carried")) {
		const value = given[key];
		if (typeof value !== "string" || value === "") return null;
		out[key] = value;
	}
	return out;
}
