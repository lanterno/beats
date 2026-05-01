/**
 * Tests for the shared API client. Locks in the contract that
 * matters most for end-to-end UX: the API's unified error envelope
 * (`{detail, code, fields?}`) lands on a typed ApiError that forms
 * and toasts can read structurally — and the rendered `err.message`
 * carries enough detail that a caller who just shows the message
 * gets useful feedback.
 *
 * The 422 path is the one that broke silently before this test
 * file existed: validation errors landed on the wire with the
 * fields[] array, but ApiError dropped them, so a form showing
 * `err.message` would say only "Validation failed for 2 fields"
 * with no indication of which.
 */
import "fake-indexeddb/auto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearAll, listPending } from "../lib/mutationQueue";
import { ApiError, type ApiErrorField, apiClient, apiMutate, describeError } from "./client";

const originalFetch = globalThis.fetch;

afterEach(() => {
	globalThis.fetch = originalFetch;
	vi.restoreAllMocks();
});

function mockFetchOnce(
	status: number,
	body: unknown,
	init?: { ok?: boolean; statusText?: string },
) {
	const response = {
		ok: init?.ok ?? status < 400,
		status,
		statusText: init?.statusText ?? "",
		json: () => Promise.resolve(body),
	} as Response;
	globalThis.fetch = vi.fn(() => Promise.resolve(response)) as unknown as typeof fetch;
}

function mockFetchOnceNonJson(status: number, statusText = "") {
	// Simulates a proxy 502 that returns HTML instead of JSON. The
	// client should still produce a usable ApiError rather than crash
	// on the JSON decode.
	const response = {
		ok: false,
		status,
		statusText,
		json: () => Promise.reject(new Error("not json")),
	} as Response;
	globalThis.fetch = vi.fn(() => Promise.resolve(response)) as unknown as typeof fetch;
}

describe("apiClient — error handling", () => {
	it("parses {detail, code} from the API error envelope onto ApiError", async () => {
		mockFetchOnce(404, { detail: "Project not found", code: "PROJECT_NOT_FOUND" });

		await expect(apiClient("/api/projects/missing")).rejects.toMatchObject({
			statusCode: 404,
			code: "PROJECT_NOT_FOUND",
			message: "Project not found",
		});
	});

	it("surfaces fields[] on 422 validation errors and renders them in err.message", async () => {
		// The whole point of this iteration: a form caller reading
		// err.message should see WHICH fields failed, not just
		// "Validation failed for 2 fields".
		const fields: ApiErrorField[] = [
			{ path: "name", message: "field required", type: "missing" },
			{ path: "email", message: "invalid format", type: "value_error" },
		];
		mockFetchOnce(422, {
			detail: "Validation failed for 2 fields",
			code: "VALIDATION_ERROR",
			fields,
		});

		try {
			await apiClient("/api/projects", { method: "POST", body: "{}" });
			throw new Error("expected rejection");
		} catch (err) {
			expect(err).toBeInstanceOf(ApiError);
			const apiErr = err as ApiError;
			expect(apiErr.statusCode).toBe(422);
			expect(apiErr.code).toBe("VALIDATION_ERROR");
			expect(apiErr.fields).toEqual(fields);
			expect(apiErr.isValidationError()).toBe(true);
			// Rendered message includes the field details so the
			// generic "show err.message" path is informative.
			expect(apiErr.message).toContain("name (field required)");
			expect(apiErr.message).toContain("email (invalid format)");
			expect(apiErr.message.startsWith("Validation failed for 2 fields")).toBe(true);
		}
	});

	it("falls back to status text when the body has no detail", async () => {
		mockFetchOnce(500, {}, { statusText: "Internal Server Error" });

		await expect(apiClient("/api/anything")).rejects.toMatchObject({
			statusCode: 500,
			message: "Request failed: Internal Server Error",
			fields: undefined,
		});
	});

	it("survives a non-JSON error body without crashing on the decode", async () => {
		mockFetchOnceNonJson(502, "Bad Gateway");

		await expect(apiClient("/api/anything")).rejects.toMatchObject({
			statusCode: 502,
			message: "Request failed: Bad Gateway",
		});
	});

	it("does not attach fields when the body's fields key is not an array", async () => {
		// Defensive: a non-array `fields` (older API, hand-crafted error)
		// must not crash the array-pathway. We just skip it.
		mockFetchOnce(400, { detail: "Bad request", code: "BAD_REQUEST", fields: "not an array" });

		const err = (await apiClient("/api/anything").catch((e) => e)) as ApiError;
		expect(err).toBeInstanceOf(ApiError);
		expect(err.fields).toBeUndefined();
		expect(err.message).toBe("Bad request");
	});

	it("does not append empty field-detail garbage when each field is blank", async () => {
		// If the server hand-crafted an envelope with empty path AND
		// message in every entry (shouldn't happen in practice, but
		// shouldn't break us either), the rendered message stays clean.
		mockFetchOnce(422, {
			detail: "Validation failed",
			code: "VALIDATION_ERROR",
			fields: [{ path: "", message: "", type: "" }],
		});

		const err = (await apiClient("/api/anything").catch((e) => e)) as ApiError;
		expect(err.message).toBe("Validation failed");
	});
});

describe("ApiError predicates", () => {
	it("isValidationError returns true for 422 only", () => {
		expect(new ApiError(422, "x").isValidationError()).toBe(true);
		expect(new ApiError(400, "x").isValidationError()).toBe(false);
		expect(new ApiError(500, "x").isValidationError()).toBe(false);
	});

	it("existing predicates still match their status codes", () => {
		expect(new ApiError(404, "x").isNotFound()).toBe(true);
		expect(new ApiError(401, "x").isUnauthorized()).toBe(true);
		expect(new ApiError(409, "x").isConflict()).toBe(true);
		expect(new ApiError(400, "x").isBadRequest()).toBe(true);
	});
});

// Auth side-effect: a 401 triggers a session-token clear + redirect.
// Asserting it here would require mocking the auth store and JSDOM's
// window.location, which is more harness than this iteration warrants
// — covered by the e2e suite (login + token-expiry path).
describe("apiClient — 401 side effect (smoke)", () => {
	beforeEach(() => {
		// jsdom's window.location.replace is a noop but throws on some
		// jsdom versions; pin a stub so the redirect doesn't crash
		// the test.
		Object.defineProperty(window, "location", {
			configurable: true,
			value: { ...window.location, replace: vi.fn() },
		});
	});

	it("still throws the typed ApiError on 401 (so callers can catch it)", async () => {
		mockFetchOnce(401, { detail: "Token expired", code: "UNAUTHORIZED" });

		const err = (await apiClient("/api/anything").catch((e) => e)) as ApiError;
		expect(err).toBeInstanceOf(ApiError);
		expect(err.isUnauthorized()).toBe(true);
		expect(err.code).toBe("UNAUTHORIZED");
	});
});

// apiMutate is the offline-aware mutation wrapper used by every
// write path (timer start/stop, beat update, intentions, …). The
// "queue vs throw" decision is the load-bearing contract: a 4xx
// reached the server and queueing it would compound user errors,
// while a TypeError means the request never went out and queueing
// is the whole point. These tests pin both branches so a refactor
// of isNetworkError can't silently flip them.
describe("apiMutate — queue vs throw", () => {
	beforeEach(async () => {
		// fake-indexeddb persists across tests in the same file; wipe
		// the queue so each case starts from zero pending mutations.
		await clearAll();
	});

	it("returns status:'sent' with the response body on a 200", async () => {
		mockFetchOnce(200, { id: "p1", name: "Beats" });

		const result = await apiMutate<{ id: string }>("POST", "/api/projects", {
			name: "Beats",
		});

		expect(result.status).toBe("sent");
		expect(result.data).toEqual({ id: "p1", name: "Beats" });
		expect(result.clientId.length).toBeGreaterThan(8);
		expect(await listPending()).toHaveLength(0);
	});

	it("attaches X-Client-Id by default for server-side idempotency", async () => {
		// The sync engine relies on this header so a replayed mutation
		// doesn't double-write. Default is on; opt-out via
		// `idempotent: false`.
		const fetchSpy = vi.fn(async () => ({
			ok: true,
			status: 200,
			statusText: "",
			json: () => Promise.resolve({}),
		}));
		globalThis.fetch = fetchSpy as unknown as typeof fetch;

		await apiMutate("POST", "/api/timer/start", {});

		const init1 = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		const headers = init1.headers as Record<string, string>;
		expect(headers["X-Client-Id"]).toBeTruthy();
	});

	it("omits X-Client-Id when idempotent:false is set", async () => {
		const fetchSpy = vi.fn(async () => ({
			ok: true,
			status: 200,
			statusText: "",
			json: () => Promise.resolve({}),
		}));
		globalThis.fetch = fetchSpy as unknown as typeof fetch;

		await apiMutate("POST", "/api/anything", {}, { idempotent: false });

		const init2 = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		const headers = (init2.headers ?? {}) as Record<string, string>;
		expect(headers["X-Client-Id"]).toBeUndefined();
	});

	it("throws ApiError on 4xx and does NOT queue (request reached the server)", async () => {
		// The whole reason apiMutate distinguishes network failure
		// from response failure: queueing a 400 would replay it
		// every reconnect and burn the user with the same error
		// repeatedly. Lock the throw-not-queue branch.
		mockFetchOnce(400, { detail: "name too short", code: "VALIDATION_ERROR" });

		await expect(apiMutate("POST", "/api/projects", { name: "" })).rejects.toBeInstanceOf(ApiError);
		expect(await listPending()).toHaveLength(0);
	});

	it("queues on TypeError (network unreachable) instead of throwing", async () => {
		// fetch() throws a TypeError when DNS fails or there's no
		// connectivity. apiMutate catches this and writes the
		// mutation to IndexedDB; the sync engine drains it on
		// reconnect.
		globalThis.fetch = vi.fn(() =>
			Promise.reject(new TypeError("Failed to fetch")),
		) as unknown as typeof fetch;

		const result = await apiMutate("POST", "/api/timer/start", { project_id: "p1" });

		expect(result.status).toBe("queued");
		expect(result.data).toBeUndefined();
		expect(result.queueError).toBeUndefined();

		const pending = await listPending();
		expect(pending).toHaveLength(1);
		expect(pending[0].method).toBe("POST");
		expect(pending[0].path).toBe("/api/timer/start");
		expect(pending[0].body).toEqual({ project_id: "p1" });
		expect(pending[0].clientId).toBe(result.clientId);
	});

	it("respects queueOnFailure:false by throwing the network error", async () => {
		// Some callers (e.g. an explicit "save & retry" UI button)
		// want to handle the failure inline rather than silently
		// queue. Opt-out path.
		const networkErr = new TypeError("Failed to fetch");
		globalThis.fetch = vi.fn(() => Promise.reject(networkErr)) as unknown as typeof fetch;

		await expect(apiMutate("POST", "/api/anything", {}, { queueOnFailure: false })).rejects.toThrow(
			"Failed to fetch",
		);
		expect(await listPending()).toHaveLength(0);
	});

	it("uses caller-supplied clientId verbatim (so retries dedupe)", async () => {
		// The sync engine reuses the original clientId when replaying
		// — letting the caller pin the id is the contract that
		// makes retry-after-queue safe.
		mockFetchOnce(200, {});

		const result = await apiMutate("POST", "/api/anything", {}, { clientId: "fixed-123" });

		expect(result.clientId).toBe("fixed-123");
	});
});

// describeError is the small helper toasts call from `onError`
// handlers. The whole reason for it: ApiError's `message` already
// includes detail + code + 422 fields[] suffix, so passing
// err.message through is exactly what we want — but we need a
// fallback for non-Error values (a thrown string, a stuck-in-the-
// rare-corners undefined).
describe("describeError", () => {
	it("returns ApiError.message verbatim (with all the envelope detail)", () => {
		const err = new ApiError(404, "Project archived [PROJECT_ARCHIVED]", "PROJECT_ARCHIVED");
		expect(describeError(err, "Failed to save")).toBe("Project archived [PROJECT_ARCHIVED]");
	});

	it("returns plain Error.message verbatim", () => {
		// Non-API errors (network TypeError, manual `new Error(...)`)
		// still have a useful message; surface it.
		expect(describeError(new Error("Failed to fetch"), "x")).toBe("Failed to fetch");
	});

	it("falls back when the value is not an Error", () => {
		// Defensive: a thrown string or undefined would become "[object
		// Object]" or "undefined" if we naively String()'d it. Use the
		// generic toast text instead.
		expect(describeError("oops", "Failed to save")).toBe("Failed to save");
		expect(describeError(undefined, "Failed to save")).toBe("Failed to save");
		expect(describeError(null, "Failed to save")).toBe("Failed to save");
		expect(describeError({ detail: "wat" }, "Failed to save")).toBe("Failed to save");
	});

	it("falls back when an Error has an empty message", () => {
		// An exotic case (`throw new Error()`) — the empty message would
		// produce a blank toast, which reads worse than the fallback.
		expect(describeError(new Error(""), "Failed to save")).toBe("Failed to save");
	});
});
