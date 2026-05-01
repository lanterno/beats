/**
 * Pure helper for building the deep link the "Beats: Open Insights"
 * command opens in the system browser. Lives outside extension.ts so
 * it has no `vscode` import — that lets us test it with plain
 * `node --test` instead of standing up @vscode/test-electron for one
 * URL.
 *
 * The URL scheme deliberately matches what useUrlParam writes when the
 * user clicks a filter chip on the web — so a deep link from the
 * editor and a click on the page produce the same browser address bar.
 */

/**
 * Build the Insights deep link from the configured web base URL and
 * the current workspace path.
 *
 * - `base` is normalized: trailing slash stripped so the result is
 *   always `<base>/insights` not `<base>//insights`.
 * - `repo` is encoded via encodeURIComponent so paths with spaces /
 *   `&` / `=` round-trip into the URL safely. Same encoding the web
 *   client uses when serializing repo into the search string.
 * - When `repo` is null/empty the bare `<base>/insights` URL is
 *   returned — opening the unfiltered Insights view.
 */
export function buildInsightsUrl(base: string, repo: string | null): string {
	const trimmed = base.replace(/\/$/, "");
	if (!repo) return `${trimmed}/insights`;
	return `${trimmed}/insights?repo=${encodeURIComponent(repo)}`;
}
