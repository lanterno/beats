/**
 * API Client
 * Centralized HTTP client with error handling and authentication.
 * Mirrors the backend's exception handling pattern.
 */

import { endSession, sessionToken } from "@/shared/session";
import { config } from "../config";
import {
	enqueueMutation,
	type HttpMethod,
	hasQueuedWork,
	newClientId,
	type PendingMutation,
} from "../lib/mutationQueue";

/**
 * One entry in the {@link ApiError.fields} array. Mirrors the API's
 * 422 validation envelope (api/src/beats/api/errors.py:95) so a form
 * can show inline messages without re-parsing the response.
 */
export interface ApiErrorField {
	/** Dot-joined path of the offending field, e.g. "name" or "items.0.qty". */
	path: string;
	/** Human message from pydantic, e.g. "field required". */
	message: string;
	/** Pydantic validation type, e.g. "missing", "string_too_short". */
	type: string;
}

/**
 * API Error class for handling backend errors consistently.
 * Similar to backend's DomainException hierarchy.
 */
export class ApiError extends Error {
	constructor(
		public readonly statusCode: number,
		message: string,
		public readonly code?: string,
		public readonly fields?: ApiErrorField[],
	) {
		super(message);
		this.name = "ApiError";
	}

	/**
	 * Check if error is a specific type based on status code
	 */
	isNotFound(): boolean {
		return this.statusCode === 404;
	}

	isUnauthorized(): boolean {
		return this.statusCode === 401;
	}

	isConflict(): boolean {
		return this.statusCode === 409;
	}

	isBadRequest(): boolean {
		return this.statusCode === 400;
	}

	isValidationError(): boolean {
		return this.statusCode === 422;
	}
}

/**
 * Surface an API error's human message, falling back to a caller-
 * supplied generic when the error wasn't an Error or carried no
 * message. Use this in `onError` handlers so toasts read like
 * "Project archived [PROJECT_ARCHIVED]" instead of the generic
 * "Failed to save"; an ApiError's `message` already includes the
 * envelope's detail + code + (for 422) fields[] suffix.
 *
 * Pass a fallback that makes sense without context — it's what the
 * user sees when something exotic blew up (a thrown string, a
 * network TypeError before the wrapper got to run, etc.).
 */
export function describeError(err: unknown, fallback: string): string {
	if (err instanceof Error && err.message) {
		return err.message;
	}
	return fallback;
}

/**
 * The per-field messages of a 422, keyed by their dot-joined path
 * ("contract.terms.0.percentage"), so a form can pin each one next to
 * the right input. Empty for anything that is not an ApiError with
 * `fields`; a path the API reports twice keeps its first message.
 */
export function apiFieldErrors(err: unknown): Record<string, string> {
	const out: Record<string, string> = {};
	if (!(err instanceof ApiError) || !err.fields) return out;
	for (const f of err.fields) {
		const path = (f.path ?? "").trim();
		const message = (f.message ?? "").trim();
		if (!message || out[path] !== undefined) continue;
		out[path] = message;
	}
	return out;
}

/**
 * Render a 422-style fields array as a human suffix appended to the
 * envelope's `detail`. Skips empty paths/messages defensively so a
 * malformed entry doesn't produce "name (), email ()" garbage.
 */
function appendFieldDetails(detail: string, fields: ApiErrorField[]): string {
	const parts: string[] = [];
	for (const f of fields) {
		const path = (f.path ?? "").trim();
		const message = (f.message ?? "").trim();
		if (!path && !message) continue;
		if (path && message) parts.push(`${path} (${message})`);
		else parts.push(path || message);
	}
	return parts.length === 0 ? detail : `${detail}: ${parts.join(", ")}`;
}

/**
 * Get headers for authenticated JSON requests.
 * Uses JWT Bearer token from WebAuthn session.
 */
function getAuthHeaders(): Record<string, string> {
	const token = sessionToken();

	if (token) {
		return {
			"Content-Type": "application/json",
			Authorization: `Bearer ${token}`,
		};
	}

	return {
		"Content-Type": "application/json",
	};
}

/**
 * Get headers for read-only requests (auth required for all endpoints)
 */
function getReadHeaders(): Record<string, string> {
	const token = sessionToken();
	const headers: Record<string, string> = { Accept: "application/json" };

	if (token) {
		headers.Authorization = `Bearer ${token}`;
	}

	return headers;
}

/**
 * The ApiError a non-ok response stands for, read off the envelope
 * (`{detail, code, fields?}`). A 401 also ends the session and sends the
 * browser home, whoever made the call: an expired token is the same on
 * every route.
 */
export async function apiErrorFrom(response: Response): Promise<ApiError> {
	// Handle expired/invalid session tokens
	if (response.status === 401) {
		endSession();
		window.location.replace("/");
	}

	const errorBody = await response.json().catch(() => ({}));
	const fields = Array.isArray(errorBody.fields)
		? (errorBody.fields as ApiErrorField[])
		: undefined;
	const baseMessage =
		errorBody.detail || errorBody.message || `Request failed: ${response.statusText}`;
	// Append the per-field messages to the human message so any
	// caller that just renders err.message gets useful detail —
	// "Validation failed for 2 fields: name (field required), email
	// (invalid format)". Forms that need structured access still
	// have err.fields untouched.
	const message =
		fields && fields.length > 0 ? appendFieldDetails(baseMessage, fields) : baseMessage;
	return new ApiError(response.status, message, errorBody.code, fields);
}

export async function apiClient<T>(endpoint: string, options?: RequestInit): Promise<T> {
	const isWrite = options?.method && options.method !== "GET";
	const defaultHeaders = isWrite ? getAuthHeaders() : getReadHeaders();

	const response = await fetch(`${config.apiBaseUrl}${endpoint}`, {
		...options,
		headers: {
			...defaultHeaders,
			...options?.headers,
		},
	});

	if (!response.ok) {
		throw await apiErrorFrom(response);
	}

	// Handle empty responses (204 No Content)
	if (response.status === 204) {
		return undefined as T;
	}

	return response.json();
}

export function get<T>(endpoint: string): Promise<T> {
	return apiClient<T>(endpoint, { method: "GET" });
}

export function post<T>(endpoint: string, body?: unknown): Promise<T> {
	return apiClient<T>(endpoint, {
		method: "POST",
		body: body ? JSON.stringify(body) : undefined,
	});
}

export function put<T>(endpoint: string, body: unknown): Promise<T> {
	return apiClient<T>(endpoint, {
		method: "PUT",
		body: JSON.stringify(body),
	});
}

export function patch<T>(endpoint: string, body: unknown): Promise<T> {
	return apiClient<T>(endpoint, {
		method: "PATCH",
		body: JSON.stringify(body),
	});
}

export function del<T>(endpoint: string): Promise<T> {
	return apiClient<T>(endpoint, { method: "DELETE" });
}

/**
 * A GET that never carries the session.
 *
 * The one public route the SPA reads is a report link
 * (`/api/reports/{token}`, docs/billing.md phase 1c). The token in the URL
 * is the whole of its authorisation, and the page has to work for a client
 * who has no account at all. Attaching the owner's bearer token when they
 * happen to be signed in would make the page behave differently for them
 * than for the person they sent it to, which is the one thing a "see what
 * your client sees" page must not do.
 *
 * Not `get` with headers overridden: `apiClient` spreads its own headers
 * first, so an override can replace `Authorization` but never remove it.
 */
export async function getPublic<T>(endpoint: string): Promise<T> {
	const response = await fetch(`${config.apiBaseUrl}${endpoint}`, {
		method: "GET",
		headers: { Accept: "application/json" },
	});

	if (!response.ok) {
		throw await apiErrorFrom(response);
	}

	return response.json();
}

// Offline-aware mutation wrapper (Stage 1.4)

/**
 * Signals a network-layer failure so callers can branch on "queue vs throw".
 * Does not wrap 4xx/5xx responses — those indicate the request reached the
 * server, and queueing them would compound user-facing errors.
 */
function isNetworkError(err: unknown): boolean {
	if (err instanceof TypeError) return true; // fetch throws TypeError on network failure
	if (typeof navigator !== "undefined" && navigator.onLine === false) return true;
	return false;
}

export interface MutateOptions {
	/** Attach an X-Client-Id for server-side idempotency. Defaults to true. */
	idempotent?: boolean;
	/** Override the auto-generated client id (useful for retries). */
	clientId?: string;
	/**
	 * Opt out of queuing entirely. Defaults to true. `false` also skips the
	 * order check: the caller handles failure inline and accepts that its
	 * write may land ahead of queued ones.
	 */
	queueOnFailure?: boolean;
}

export interface MutateResult<T> {
	status: "sent" | "queued";
	data?: T;
	clientId: string;
	queueError?: string;
}

/**
 * Write the mutation to IndexedDB and answer `{status: "queued"}`. A queue
 * that cannot be written (private mode, quota) still answers "queued" with
 * `queueError` set — the caller already updated its optimistic state, and
 * throwing here would roll that back for a storage problem, not an API one.
 */
async function queueBehind<T>(
	method: HttpMethod,
	path: string,
	body: unknown,
	clientId: string,
): Promise<MutateResult<T>> {
	try {
		const pending: Omit<PendingMutation, "id" | "enqueuedAt" | "attempts"> = {
			method,
			path,
			body,
			clientId,
		};
		await enqueueMutation(pending);
		return { status: "queued", clientId };
	} catch (queueErr) {
		const message = queueErr instanceof Error ? queueErr.message : String(queueErr);
		return { status: "queued", clientId, queueError: message };
	}
}

/**
 * Perform a mutation with offline queueing + idempotency.
 *
 * - Attaches `X-Client-Id` so the server can de-dupe replays.
 * - While earlier writes wait in the queue, or the sync engine is draining
 *   them, joins the back of the queue instead of sending, and returns
 *   `{status: "queued"}` — otherwise this write could land before them
 *   (a new start before a queued stop). A queued entry leaves the store only
 *   after the server applies it, so a write arriving mid-drain still sees the
 *   ones not yet landed.
 * - On a TypeError (network failure) or navigator.onLine === false, writes the
 *   mutation to IndexedDB and returns `{status: "queued"}`. The sync engine
 *   drains the queue on reconnect.
 * - HTTP errors (4xx/5xx) propagate as `ApiError` and are NOT queued.
 */
export async function apiMutate<T>(
	method: HttpMethod,
	path: string,
	body: unknown,
	options: MutateOptions = {},
): Promise<MutateResult<T>> {
	const { idempotent = true, queueOnFailure = true } = options;
	const clientId = options.clientId ?? newClientId();

	if (queueOnFailure && (await hasQueuedWork())) {
		return queueBehind<T>(method, path, body, clientId);
	}

	const headers: Record<string, string> = {};
	if (idempotent) headers["X-Client-Id"] = clientId;

	try {
		const data = await apiClient<T>(path, {
			method,
			body: body === undefined ? undefined : JSON.stringify(body),
			headers,
		});
		return { status: "sent", data, clientId };
	} catch (err) {
		if (queueOnFailure && isNetworkError(err)) {
			return queueBehind<T>(method, path, body, clientId);
		}
		throw err;
	}
}

/**
 * Replay a queued mutation exactly once. Used by the sync engine.
 * Does not re-queue on failure — the engine decides whether to retry.
 */
export async function replayMutation(pending: PendingMutation): Promise<void> {
	await apiClient(pending.path, {
		method: pending.method,
		body: pending.body === undefined ? undefined : JSON.stringify(pending.body),
		headers: { "X-Client-Id": pending.clientId },
	});
}
