/**
 * API Client
 * Centralized HTTP client with error handling and authentication.
 * Mirrors the backend's exception handling pattern.
 */

import { getSessionToken } from "@/features/auth/stores/authStore";
import { config } from "../config";

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
			window.location.href = "/login";
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
