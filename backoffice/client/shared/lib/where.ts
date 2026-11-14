/**
 * Which deployment the operator is looking at, from the hostname the page
 * was served from.
 *
 * The back office wears the app's look, so the thing that says "this is the
 * control plane" is a label rather than a colour (docs/backoffice.md § The
 * UI) — and the label has to say *which* control plane, because the buttons
 * here suspend accounts and queue erasures. There is no API field for this:
 * one image serves both, and the only honest source is where the browser
 * is. `backoffice.lifepete.com` is the production hostname (docs/backoffice.md
 * § Deployment); the `run.app` URL stays up behind the same IAP and is the
 * same live platform, so it reads live too.
 */

export interface Deployment {
	label: string;
	/** Acting here acts on real people. */
	live: boolean;
}

const PRODUCTION = "backoffice.lifepete.com";

export function deployment(hostname: string): Deployment {
	const host = hostname.toLowerCase();
	if (host === PRODUCTION) return { label: "Production", live: true };
	// Cloud Run's own URL for the same service, which IAP also fronts. A
	// write from it answers 403 (OPERATOR_ORIGIN is the hostname above), but
	// what is read there is production's data.
	if (host.endsWith(".run.app")) return { label: "Production, run.app", live: true };
	return { label: "Local", live: false };
}
