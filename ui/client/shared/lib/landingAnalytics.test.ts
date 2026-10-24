import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// What reaches Cloudflare is the point of these tests: the beacon may run on the
// signed-out landing page and nowhere else, and once it has, the landing page is
// left by replacing the document (landingAnalytics.ts says why).

const realLocation = window.location;
const replace = vi.fn();

function at(pathname: string) {
	Object.defineProperty(window, "location", {
		configurable: true,
		value: { ...realLocation, pathname, replace },
	});
}

function referredBy(url: string) {
	Object.defineProperty(document, "referrer", { configurable: true, value: url });
}

function beacons() {
	return document.head.querySelectorAll<HTMLScriptElement>(
		'script[src="https://static.cloudflareinsights.com/beacon.min.js"]',
	);
}

/** A fresh copy of the module, so `loaded` and the build-time token start over. */
async function loadModule(token: string | undefined) {
	vi.stubEnv("VITE_CF_WEB_ANALYTICS_TOKEN", token);
	vi.resetModules();
	return import("./landingAnalytics");
}

beforeEach(() => {
	replace.mockReset();
	for (const s of beacons()) s.remove();
});

afterEach(() => {
	vi.unstubAllEnvs();
	vi.unstubAllGlobals();
	// Drops the own property, so Document's getter answers again.
	delete (document as { referrer?: string }).referrer;
	Object.defineProperty(window, "location", { configurable: true, value: realLocation });
});

describe("loadLandingAnalytics", () => {
	it("adds the beacon on / with the token and the SPA tracking off, once", async () => {
		at("/");
		const { loadLandingAnalytics } = await loadModule("site-token");
		loadLandingAnalytics();
		loadLandingAnalytics();

		const found = beacons();
		expect(found).toHaveLength(1);
		expect(JSON.parse(found[0].dataset.cfBeacon ?? "")).toEqual({
			token: "site-token",
			spa: false,
		});
	});

	it("adds nothing on any path but /", async () => {
		// A report link's secret is in its path.
		at("/r/secret-token");
		const { loadLandingAnalytics } = await loadModule("site-token");
		loadLandingAnalytics();
		expect(beacons()).toHaveLength(0);
	});

	it("adds nothing on / when the document began on another path", async () => {
		// Back would show that path again, in the document the beacon runs in.
		at("/organisations/join/invite-token");
		const { loadLandingAnalytics } = await loadModule("site-token");
		at("/");
		loadLandingAnalytics();
		expect(beacons()).toHaveLength(0);
	});

	it("adds nothing once the landing page has been left in the SPA", async () => {
		// Signed in on arrival, then signed out back to /: the history holds /app.
		at("/");
		const { leaveLanding, loadLandingAnalytics } = await loadModule("site-token");
		leaveLanding("/app", vi.fn());
		loadLandingAnalytics();
		expect(beacons()).toHaveLength(0);
	});

	it("adds nothing when another page of this site opened /", async () => {
		// Signing out or a 401 replaces the document with /, and the page left
		// behind would be the referrer.
		at("/");
		referredBy(`${realLocation.origin}/r/secret-token`);
		const { loadLandingAnalytics } = await loadModule("site-token");
		loadLandingAnalytics();
		expect(beacons()).toHaveLength(0);
	});

	it("adds the beacon when another site linked to /", async () => {
		at("/");
		referredBy("https://news.example/thread");
		const { loadLandingAnalytics } = await loadModule("site-token");
		loadLandingAnalytics();
		expect(beacons()).toHaveLength(1);
	});

	it("adds nothing when the build has no token", async () => {
		at("/");
		const { loadLandingAnalytics } = await loadModule("");
		loadLandingAnalytics();
		expect(beacons()).toHaveLength(0);
	});

	it("adds nothing under Do Not Track", async () => {
		at("/");
		vi.stubGlobal("navigator", { ...navigator, doNotTrack: "1" });
		const { loadLandingAnalytics } = await loadModule("site-token");
		loadLandingAnalytics();
		expect(beacons()).toHaveLength(0);
	});

	it("adds nothing under Global Privacy Control", async () => {
		at("/");
		vi.stubGlobal("navigator", { ...navigator, globalPrivacyControl: true });
		const { loadLandingAnalytics } = await loadModule("site-token");
		loadLandingAnalytics();
		expect(beacons()).toHaveLength(0);
	});
});

describe("leaveLanding", () => {
	it("navigates in the SPA when the beacon never loaded", async () => {
		at("/");
		const { leaveLanding } = await loadModule("");
		const navigate = vi.fn();
		leaveLanding("/app", navigate);

		expect(navigate).toHaveBeenCalledWith("/app", { replace: true });
		expect(replace).not.toHaveBeenCalled();
	});

	it("replaces the document once the beacon has loaded, so it unloads on /", async () => {
		at("/");
		const { leaveLanding, loadLandingAnalytics } = await loadModule("site-token");
		loadLandingAnalytics();
		const navigate = vi.fn();
		leaveLanding("/organisations/join/abc", navigate);

		expect(replace).toHaveBeenCalledWith("/organisations/join/abc");
		expect(navigate).not.toHaveBeenCalled();
	});
});
