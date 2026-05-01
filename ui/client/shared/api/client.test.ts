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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, type ApiErrorField, apiClient } from "./client";

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
