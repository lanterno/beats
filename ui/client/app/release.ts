/**
 * Moves an open page onto a new release of the app (ui/README.md § PWA).
 *
 * The service worker precaches the built app and answers every navigation from
 * that precache, so a visit after a deploy first renders whichever release the
 * worker last stored, however old. The worker finds the new release while that
 * page loads and takes over at once (vite-plugin-pwa's `autoUpdate`: skipWaiting
 * and clientsClaim), but a page keeps running the code it loaded. Left there, it
 * stays on the old release until the next full load, calling routes the API may
 * have changed or dropped since: on 2026-11-14 a visitor's page was still asking
 * for one removed on 2026-10-15.
 *
 * So the page notes when a newer worker takes control, and loads the new release
 * at its next change of page rather than at once: whatever is half-typed on this
 * one is never thrown away, and a page being left is going anyway. An open tab
 * also asks for a new worker every hour, since otherwise only a navigation makes
 * the browser look.
 */

const LOOK_EVERY_MS = 60 * 60 * 1000;

let newRelease = false;

/** Whether a newer release has taken control since this page loaded. */
export function newReleaseWaiting(): boolean {
	return newRelease;
}

/**
 * Registers the app's service worker, and notes when a newer one takes control.
 *
 * The first worker a browser installs takes control of the page that installed
 * it too, and that is no new release: the page came from the network. So a
 * change of worker counts only once a worker was active before.
 */
export async function watchForNewRelease(sw: ServiceWorkerContainer): Promise<void> {
	let replacing = Boolean((await sw.getRegistration())?.active);
	sw.addEventListener("controllerchange", () => {
		if (replacing) newRelease = true;
		replacing = true;
	});
	const registration = await sw.register("/sw.js", { scope: "/" });
	setInterval(() => {
		// Offline, or the server between deploys: the next hour asks again.
		registration.update().catch(() => {});
	}, LOOK_EVERY_MS);
}
