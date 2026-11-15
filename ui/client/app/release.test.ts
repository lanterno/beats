import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/** A browser's service workers: one registration, or none yet. */
class FakeWorkers extends EventTarget {
	constructor(private readonly activeBefore: boolean) {
		super();
	}

	async getRegistration() {
		return this.activeBefore ? { active: {} } : undefined;
	}

	async register() {
		return { update: async () => undefined };
	}

	/** A worker takes control of the page (clientsClaim). */
	takeControl() {
		this.dispatchEvent(new Event("controllerchange"));
	}
}

// The module holds what one page has seen, so each case loads a fresh copy.
async function freshPage() {
	vi.resetModules();
	return import("./release");
}

describe("watchForNewRelease", () => {
	// The hourly look for a new worker is an interval; it must not outlive a case.
	beforeEach(() => {
		vi.useFakeTimers();
	});
	afterEach(() => {
		vi.useRealTimers();
	});

	it("a page served by an earlier worker waits for the new release once a newer worker takes control", async () => {
		const { watchForNewRelease, newReleaseWaiting } = await freshPage();
		const workers = new FakeWorkers(true);
		await watchForNewRelease(workers as unknown as ServiceWorkerContainer);

		expect(newReleaseWaiting()).toBe(false);
		workers.takeControl();
		expect(newReleaseWaiting()).toBe(true);
	});

	it("the first worker a browser installs is no new release, and the next one is", async () => {
		const { watchForNewRelease, newReleaseWaiting } = await freshPage();
		const workers = new FakeWorkers(false);
		await watchForNewRelease(workers as unknown as ServiceWorkerContainer);

		workers.takeControl();
		expect(newReleaseWaiting()).toBe(false);
		workers.takeControl();
		expect(newReleaseWaiting()).toBe(true);
	});
});
