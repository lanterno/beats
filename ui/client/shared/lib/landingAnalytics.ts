/**
 * Cloudflare Web Analytics, on the signed-out landing page and nowhere else
 * (AHM-110).
 *
 * The beacon sends paths, never a query or a fragment: the page's own and the
 * referrer's. It reads the page's path when it sends, not when it loads: once on
 * load, and again with the page's Web Vitals the first time the tab is hidden,
 * whichever route the SPA is on by then. Its own SPA tracking off (`spa: false`)
 * does not stop that second send. Every other route has to stay away from
 * Cloudflare — `/r/<token>` carries a report link's secret in its path, an
 * invitation its token, and signed-in paths carry ids — so the beacon loads only
 * in a document that:
 *
 * - began on `/` and has never left it. Back and Forward then have no other route
 *   in this document to show, and once the beacon has loaded, the landing page is
 *   left by replacing the document (`leaveLanding`), so it unloads still on `/`.
 *   An in-page anchor changes only the fragment, which the beacon drops;
 * - was not opened from another page of this site. Signing out from the command
 *   palette, or a 401 anywhere, replaces the document with `/`, and the page left
 *   behind — a project, a report link — would be the referrer.
 *
 * `FIRST_PATH` is read when this module is evaluated, which is at startup: the
 * app imports `shared/lib` before it renders.
 *
 * No token at build time — the self-hosted build, local development — means no
 * beacon. Do Not Track and Global Privacy Control are honoured here, since the
 * beacon honours neither.
 */

const TOKEN = (import.meta.env.VITE_CF_WEB_ANALYTICS_TOKEN as string | undefined) ?? "";
const BEACON_SRC = "https://static.cloudflareinsights.com/beacon.min.js";
const FIRST_PATH = window.location.pathname;

let loaded = false;
let departed = false;

function visitorDeclined(): boolean {
	const nav = navigator as Navigator & { globalPrivacyControl?: boolean };
	return nav.globalPrivacyControl === true || nav.doNotTrack === "1";
}

function openedFromThisSite(): boolean {
	if (!document.referrer) return false;
	try {
		return new URL(document.referrer).origin === window.location.origin;
	} catch {
		return true;
	}
}

/** Adds the beacon to this document if it may run here. The landing page calls it. */
export function loadLandingAnalytics(): void {
	if (loaded || departed || !TOKEN) return;
	if (FIRST_PATH !== "/" || window.location.pathname !== "/") return;
	if (openedFromThisSite() || visitorDeclined()) return;
	const script = document.createElement("script");
	script.defer = true;
	script.src = BEACON_SRC;
	script.dataset.cfBeacon = JSON.stringify({ token: TOKEN, spa: false });
	document.head.appendChild(script);
	loaded = true;
}

/**
 * Leaves the landing page for `to`: client-side when the beacon never loaded in
 * this document, and then it never will; otherwise by replacing the document, so
 * the beacon's last send still names `/`.
 */
export function leaveLanding(
	to: string,
	navigate: (to: string, options: { replace: boolean }) => void,
): void {
	if (loaded) {
		window.location.replace(to);
		return;
	}
	departed = true;
	navigate(to, { replace: true });
}
