/**
 * API Client
 * Centralized HTTP client with error handling and authentication.
 * Mirrors the backend's exception handling pattern.
 */

import { getSessionToken } from "@/features/auth/stores/authStore";
import { config } from "../config";
import {
	enqueueMutation,
	type HttpMethod,
	newClientId,
	type PendingMutation,
} from "../lib/mutationQueue";

// ============================================================================
// Error Types
// ============================================================================

/**
 * API Error class for handling backend errors consistently.
 * Similar to backend's DomainException hierarchy.
 */
export class ApiError extends Error {
	constructor(
		public readonly statusCode: number,
		message: string,
		public readonly code?: string,
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
}

// ============================================================================
// Request Helpers
// ============================================================================

/**
 * Get headers for authenticated JSON requests.
 * Uses JWT Bearer token from WebAuthn session.
 */
function getAuthHeaders(): Record<string, string> {
	const sessionToken = getSessionToken();

	if (sessionToken) {
		return {
			"Content-Type": "application/json",
			Authorization: `Bearer ${sessionToken}`,
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
	const sessionToken = getSessionToken();
	const headers: Record<string, string> = { Accept: "application/json" };

	if (sessionToken) {
		headers.Authorization = `Bearer ${sessionToken}`;
	}

	return headers;
}

// ============================================================================
// API Client
// ============================================================================

/**
 * Generic API client for making typed requests
 */
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
		// Handle expired/invalid session tokens
		if (response.status === 401) {
			const { clearSessionToken } = await import("@/features/auth/stores/authStore");
			clearSessionToken();
			window.location.replace("/");
		}

		const errorBody = await response.json().catch(() => ({}));
		const message =
			errorBody.detail || errorBody.message || `Request failed: ${response.statusText}`;
		throw new ApiError(response.status, message, errorBody.code);
	}

	// Handle empty responses (204 No Content)
	if (response.status === 204) {
		return undefined as T;
	}

	return response.json();
}

// ============================================================================
// Convenience Methods
// ============================================================================

/**
 * GET request
 */
export function get<T>(endpoint: string): Promise<T> {
	return apiClient<T>(endpoint, { method: "GET" });
}

/**
 * POST request with JSON body
 */
export function post<T>(endpoint: string, body?: unknown): Promise<T> {
	return apiClient<T>(endpoint, {
		method: "POST",
		body: body ? JSON.stringify(body) : undefined,
	});
}

/**
 * PUT request with JSON body
 */
export function put<T>(endpoint: string, body: unknown): Promise<T> {
	return apiClient<T>(endpoint, {
		method: "PUT",
		body: JSON.stringify(body),
	});
}

/**
 * PATCH request with JSON body
 */
export function patch<T>(endpoint: string, body: unknown): Promise<T> {
	return apiClient<T>(endpoint, {
		method: "PATCH",
		body: JSON.stringify(body),
	});
}

/**
 * DELETE request
 */
export function del<T>(endpoint: string): Promise<T> {
	return apiClient<T>(endpoint, { method: "DELETE" });
}

// ============================================================================
// Offline-aware mutation wrapper (Stage 1.4)
// ============================================================================

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
	/** Opt out of queuing on network failure. Defaults to true. */
	queueOnFailure?: boolean;
}

export interface MutateResult<T> {
	status: "sent" | "queued";
	data?: T;
	clientId: string;
	queueError?: string;
}

/**
 * Perform a mutation with offline queueing + idempotency.
 *
 * - Attaches `X-Client-Id` so the server can de-dupe replays.
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
