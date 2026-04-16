/**
 * Unit tests for the offline mutation queue. Uses `fake-indexeddb` to provide
 * a spec-compliant IDB in jsdom.
 */

import "fake-indexeddb/auto";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
	clearAll,
	drainPending,
	enqueueMutation,
	listPending,
	newClientId,
	type PendingMutation,
} from "./mutationQueue";

async function resetDb() {
	// Wipe the queue between tests; deleting the whole DB would race with
	// connection caching inside openDb — clearing the single store is enough.
	await clearAll();
}

beforeEach(resetDb);
afterEach(resetDb);

describe("newClientId", () => {
	it("returns a distinct string on each call", () => {
		const a = newClientId();
		const b = newClientId();
		expect(a).not.toBe(b);
		expect(a.length).toBeGreaterThan(8);
	});
});

describe("mutation queue", () => {
	const sample = (
		clientId = newClientId(),
	): Omit<PendingMutation, "id" | "enqueuedAt" | "attempts"> => ({
		method: "POST",
		path: "/api/timer/start",
		body: { time: "2026-04-16T10:00:00Z" },
		clientId,
	});

	it("enqueues and lists mutations in insertion order", async () => {
		const first = newClientId();
		const second = newClientId();
		await enqueueMutation(sample(first));
		await enqueueMutation(sample(second));

		const pending = await listPending();
		expect(pending).toHaveLength(2);
		expect(pending[0].clientId).toBe(first);
		expect(pending[1].clientId).toBe(second);
		expect(pending[0].attempts).toBe(0);
		expect(typeof pending[0].enqueuedAt).toBe("string");
	});

	it("drains successful mutations and removes them", async () => {
		await enqueueMutation(sample());
		await enqueueMutation(sample());

		const seen: string[] = [];
		const result = await drainPending(async (m) => {
			seen.push(m.clientId);
		});

		expect(result.drained).toBe(2);
		expect(result.remaining).toBe(0);
		expect(seen).toHaveLength(2);
		expect(await listPending()).toEqual([]);
	});

	it("stops draining on first error and keeps remaining in the queue", async () => {
		const a = newClientId();
		const b = newClientId();
		const c = newClientId();
		await enqueueMutation(sample(a));
		await enqueueMutation(sample(b));
		await enqueueMutation(sample(c));

		const result = await drainPending(async (m) => {
			if (m.clientId === b) throw new Error("boom");
		});

		expect(result.drained).toBe(1);
		expect(result.remaining).toBe(2);
		expect(result.error).toBe("boom");

		const remaining = await listPending();
		expect(remaining.map((p) => p.clientId)).toEqual([b, c]);
		// The failed mutation records its attempt.
		const failed = remaining.find((p) => p.clientId === b);
		expect(failed?.attempts).toBe(1);
		expect(failed?.lastError).toBe("boom");
	});

	it("preserves client id across retries (for idempotency on the server)", async () => {
		const clientId = newClientId();
		await enqueueMutation(sample(clientId));

		// Simulate a failed drain, then a successful one.
		await drainPending(async () => {
			throw new Error("offline");
		});
		const pendingAfterFail = await listPending();
		expect(pendingAfterFail[0].clientId).toBe(clientId);

		let replayedId: string | undefined;
		await drainPending(async (m) => {
			replayedId = m.clientId;
		});
		expect(replayedId).toBe(clientId);
		expect(await listPending()).toEqual([]);
	});
});
