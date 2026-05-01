/**
 * Pure helper for building the deep link the "Beats: Open Insights"
 * command opens in the system browser. Lives outside extension.ts so
 * it has no `vscode` import — that lets us test it with plain
 * `node --test` instead of standing up @vscode/test-electron for one
 * URL.
 *
 * The URL scheme deliberately matches what useUrlParam writes when the
 * user clicks a filter chip on the web (and what the daemon's
 * `beatsd open` builds via OpenFilter) — so a deep link from any of
 * those surfaces lands on the same browser address bar.
 */

/** Filter axes that can land in the URL. All optional; an empty
 * filter opens the unfiltered Insights view. AND-composed at the
 * page level via useUrlParam. */
export interface InsightsFilter {
	repo?: string | null;
	language?: string | null;
	bundle?: string | null;
}

/**
 * Build the Insights deep link from the configured web base URL and
 * an optional filter.
 *
 * - `base` is normalized: trailing slash stripped so the result is
 *   always `<base>/insights` not `<base>//insights`.
 * - Filter values are encoded via URLSearchParams so paths with
 *   spaces / `&` / `=` round-trip into the URL safely. Same encoding
 *   the web client uses when serializing into the search string.
 * - Param order is alphabetical (URLSearchParams preserves insertion
 *   order, so we set them in alphabetical key order). Two consecutive
 *   runs produce byte-identical URLs — matters for clipboard diffs
 *   and `history | grep`.
 */
export function buildInsightsUrl(base: string, filter: InsightsFilter = {}): string {
	const trimmed = base.replace(/\/$/, "");
	const params = new URLSearchParams();
	if (filter.bundle) params.set("bundle", filter.bundle);
	if (filter.language) params.set("language", filter.language);
	if (filter.repo) params.set("repo", filter.repo);
	const q = params.toString();
	return q ? `${trimmed}/insights?${q}` : `${trimmed}/insights`;
}
