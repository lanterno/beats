/**
 * Auth API Client
 * Handles WebAuthn registration and authentication API calls.
 */
import type {
	PublicKeyCredentialCreationOptionsJSON,
	PublicKeyCredentialRequestOptionsJSON,
} from "@simplewebauthn/browser";
import { config } from "@/shared/config";
import { getSessionToken } from "../stores/authStore";

// ============================================================================
// Types
// ============================================================================

export interface RegisterStartResponse {
	options: PublicKeyCredentialCreationOptionsJSON;
	user_id: string;
}

export interface LoginOptions {
	options: PublicKeyCredentialRequestOptionsJSON;
}

export interface VerifyResponse {
	verified: boolean;
	token: string;
}

export interface UserInfo {
	email: string;
	display_name: string | null;
}

// ============================================================================
// API Functions
// ============================================================================

const AUTH_BASE = `${config.apiBaseUrl}/api/auth`;

/**
 * Start registration: create user and get WebAuthn options.
 */
export async function registerStart(
	email: string,
	displayName?: string,
): Promise<RegisterStartResponse> {
	const response = await fetch(`${AUTH_BASE}/register/start`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ email, display_name: displayName }),
	});

	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(error.detail || "Failed to start registration");
	}
	return response.json();
}

/**
 * Verify registration with the server.
 */
export async function verifyRegistration(
	credential: unknown,
	deviceName?: string,
): Promise<VerifyResponse> {
	const response = await fetch(`${AUTH_BASE}/register/verify`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ credential, device_name: deviceName }),
	});

	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(error.detail || "Registration verification failed");
	}
	return response.json();
}

/**
 * Get login options from the server.
 */
export async function getLoginOptions(): Promise<LoginOptions> {
	const response = await fetch(`${AUTH_BASE}/login/options`);
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(error.detail || "Failed to get login options");
	}
	return response.json();
}

/**
 * Verify login with the server.
 */
export async function verifyLogin(credential: unknown): Promise<VerifyResponse> {
	const response = await fetch(`${AUTH_BASE}/login/verify`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ credential }),
	});

	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(error.detail || "Login verification failed");
	}
	return response.json();
}

/**
 * Logout: revoke the session token server-side.
 */
export async function logout(): Promise<void> {
	const { post } = await import("@/shared/api");
	await post("/api/auth/logout");
}

/**
 * Refresh the session token before it expires.
 */
export async function refreshToken(): Promise<string | null> {
	const token = getSessionToken();
	if (!token) return null;
	try {
		const { post } = await import("@/shared/api");
		const data = await post<{ token: string }>("/api/auth/refresh");
		return data.token;
	} catch {
		return null;
	}
}

// ============================================================================
// Credential Management (authed endpoints — use centralized client)
// ============================================================================

export interface CredentialInfo {
	id: string;
	device_name: string | null;
	created_at: string;
}

/**
 * List registered passkeys for the current user.
 */
export async function listCredentials(): Promise<CredentialInfo[]> {
	const { get } = await import("@/shared/api");
	return get<CredentialInfo[]>("/api/auth/credentials");
}

/**
 * Delete a passkey by credential ID.
 */
export async function deleteCredential(credentialId: string): Promise<void> {
	const { del } = await import("@/shared/api");
	await del(`/api/auth/credentials/${encodeURIComponent(credentialId)}`);
}

/**
 * Get current user info.
 */
export async function getCurrentUser(): Promise<UserInfo> {
	const { get } = await import("@/shared/api");
	return get<UserInfo>("/api/auth/me");
}
