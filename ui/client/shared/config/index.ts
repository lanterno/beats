/**
 * Application Configuration
 * Centralized configuration loaded from environment variables.
 */

export interface AppConfig {
	/**
	 * Base URL for the API, with no trailing slash.
	 *
	 * An empty string means "same origin" — requests go to `/api/…`
	 * relative to whatever host served the page. That is what the
	 * home.space deployment uses, where one nginx serves this bundle and
	 * proxies `/api` to the API behind it, so both share an origin.
	 * Sharing an origin is what lets the browser attach the
	 * `Home-Session` cookie to API calls at all.
	 */
	apiBaseUrl: string;
	/** Whether we're in development mode */
	isDev: boolean;
}

/**
 * Resolve the API base from the build-time env.
 *
 * An explicit `VITE_API_URL` always wins, and is checked against `undefined`
 * rather than for truthiness: an explicitly empty value is the meaningful
 * "same origin" setting, and `||` would silently swap it for the dev
 * default. A trailing "/" is stripped for the same reason — `"/" +
 * "/api/x"` would produce a protocol-relative `//api/x`.
 *
 * With nothing configured, the fallback depends on the build:
 *
 * - **dev server** — the API is a separate process on :7999.
 * - **production build** — the API is served from the same origin as this
 *   bundle, by whatever is hosting it. That is what the home.space
 *   deployment relies on, and it has to be the default rather than a flag
 *   somebody remembers to set: the `Home-Session` cookie SSO rides on is
 *   only sent same-origin, so an accidental absolute URL here disables SSO
 *   silently, with every other feature still working.
 *
 * `import.meta.env.DEV` is replaced with a literal at build time, so the
 * branch not taken is eliminated — which is what lets `ui/Dockerfile` prove
 * the localhost URL is absent from the shipped bundle.
 */
function resolveApiBaseUrl(): string {
	const raw = import.meta.env.VITE_API_URL;
	if (raw !== undefined && raw !== null) return raw.replace(/\/+$/, "");
	return import.meta.env.DEV ? "http://localhost:7999" : "";
}

/**
 * Application configuration singleton
 */
export const config: AppConfig = {
	apiBaseUrl: resolveApiBaseUrl(),
	isDev: import.meta.env.DEV,
};
