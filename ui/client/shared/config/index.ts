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
	 * self-hosted stack (`compose.selfhost.yml`) uses, where one nginx
	 * serves this bundle and proxies `/api` to the API behind it.
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
 *   bundle, by whatever is hosting it, as in the single-origin compose stack.
 *   A split deployment (lifepete.com) names its API with `VITE_API_URL`.
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
 * The API's address as someone outside this page would use it, e.g. a phone
 * scanning a pairing QR.
 *
 * `apiBaseUrl` is empty on the same-origin build, which only means something
 * to `fetch` on this page; spelled out, it is the page's own origin. A
 * configured base is returned as it is. On the split deployment that is
 * `https://api.lifepete.com`, never the SPA's origin.
 */
export function publicApiBase(apiBaseUrl: string, origin: string): string {
	return apiBaseUrl === "" ? origin : apiBaseUrl;
}

/**
 * Whether `url` names this machine (`localhost`, a `*.localhost` name,
 * 127.0.0.0/8 or `[::1]`), which another device cannot reach by that name.
 * A string that is not a URL is not loopback.
 */
export function isLoopbackUrl(url: string): boolean {
	let hostname: string;
	try {
		hostname = new URL(url).hostname.toLowerCase();
	} catch {
		return false;
	}
	return (
		hostname === "localhost" ||
		hostname.endsWith(".localhost") ||
		/^127(\.\d{1,3}){3}$/.test(hostname) ||
		hostname === "[::1]"
	);
}

export const config: AppConfig = {
	apiBaseUrl: resolveApiBaseUrl(),
	isDev: import.meta.env.DEV,
};

export { APP_NAME } from "./brand";
