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
 * Get current user info.
 */
export async function getCurrentUser(): Promise<UserInfo> {
	const token = getSessionToken();
	const response = await fetch(`${AUTH_BASE}/me`, {
		headers: token ? { Authorization: `Bearer ${token}` } : {},
	});

	if (!response.ok) {
		throw new Error("Failed to get user info");
	}
	return response.json();
}
