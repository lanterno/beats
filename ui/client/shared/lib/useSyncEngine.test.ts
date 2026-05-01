/**
 * Tests for replayPoisonAware — the wrapper that lets the sync
 * engine drop client-side-permanent failures (4xx) instead of
 * retrying them forever and blocking the rest of the queue.
 *
 * The realistic shape of the bug this guards: a user goes
 * offline, edits something with an invalid value (or a
 * since-deleted project_id), reconnects. The first replay
 * 422s. Without poison-aware handling, the queue's drain stops
 * there — every later mutation in the queue is stuck. With
 * poison-aware handling, the bad mutation is dropped (logged)
 * and drain continues.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/shared/api";
import { replayPoisonAware } from "./useSyncEngine";

const mutation = {
	id: 1,
	method: "POST" as const,
	path: "/api/projects",
	body: { name: "" },
	clientId: "abc123",
	enqueuedAt: "2026-04-30T10:00:00Z",
	attempts: 0,
};

const consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
afterEach(() => consoleWarnSpy.mockClear());

describe("replayPoisonAware", () => {
	let originalFetch: typeof globalThis.fetch;
	beforeEach(() => {
		originalFetch = globalThis.fetch;
	});
	afterEach(() => {
		globalThis.fetch = originalFetch;
	});

	function mockFetch(status: number, body: unknown = {}) {
		const response = {
			ok: status < 400,
			status,
			statusText: "",
			json: () => Promise.resolve(body),
		} as Response;
		globalThis.fetch = vi.fn(() => Promise.resolve(response)) as unknown as typeof fetch;
	}

	it("resolves silently when the server returns a 4xx (poison drop)", async () => {
		mockFetch(422, { detail: "Validation failed", code: "VALIDATION_ERROR" });
		// Should NOT throw — drainPending interprets that as
		// "drained successfully" and removes the mutation.
		await expect(replayPoisonAware(mutation)).resolves.toBeUndefined();
		// And the drop is logged so devs can spot it.
		expect(consoleWarnSpy).toHaveBeenCalled();
	});

	it("drops on every 4xx code, not just 422", async () => {
		// 400 / 401 / 403 / 404 / 409 — all permanent from a sync
		// engine's perspective. The server's saying "this won't
		// succeed, stop retrying", so we drop and continue.
		for (const status of [400, 401, 403, 404, 409]) {
			mockFetch(status, { detail: "no" });
			await expect(replayPoisonAware(mutation)).resolves.toBeUndefined();
		}
	});

	it("throws on 5xx so the queue keeps the mutation for retry", async () => {
		// Server-side errors (500/502/503) are transient. Throwing
		// keeps the mutation in the queue; the next drain retries.
		mockFetch(503, { detail: "DB unavailable", code: "SERVICE_UNAVAILABLE" });
		await expect(replayPoisonAware(mutation)).rejects.toBeInstanceOf(ApiError);
	});

	it("throws on a network error (TypeError) so the queue keeps the mutation", async () => {
		// fetch throws TypeError when DNS / TCP fails. NOT an
		// ApiError, so the type-check at line `err instanceof ApiError`
		// is false and the error bubbles up — drainPending stops
		// on this branch (the user is genuinely offline).
		globalThis.fetch = vi.fn(() =>
			Promise.reject(new TypeError("Failed to fetch")),
		) as unknown as typeof fetch;
		await expect(replayPoisonAware(mutation)).rejects.toThrow("Failed to fetch");
	});

	it("succeeds quietly on 2xx", async () => {
		// Happy path — the mutation lands and drainPending removes it.
		mockFetch(200, {});
		await expect(replayPoisonAware(mutation)).resolves.toBeUndefined();
		expect(consoleWarnSpy).not.toHaveBeenCalled();
	});
});
