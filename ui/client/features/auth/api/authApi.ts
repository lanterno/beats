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

async function authPost<T>(path: string, body?: unknown): Promise<T> {
	const init: RequestInit = { method: "POST", headers: { "Content-Type": "application/json" } };
	if (body !== undefined) init.body = JSON.stringify(body);
	const response = await fetch(`${AUTH_BASE}${path}`, init);
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(error.detail || `Request to ${path} failed`);
	}
	return response.json();
}

async function authGet<T>(path: string): Promise<T> {
	const response = await fetch(`${AUTH_BASE}${path}`);
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(error.detail || `Request to ${path} failed`);
	}
	return response.json();
}

export function registerStart(email: string, displayName?: string): Promise<RegisterStartResponse> {
	return authPost("/register/start", { email, display_name: displayName });
}

export function verifyRegistration(
	credential: unknown,
	deviceName?: string,
): Promise<VerifyResponse> {
	return authPost("/register/verify", { credential, device_name: deviceName });
}

export function getLoginOptions(): Promise<LoginOptions> {
	return authGet("/login/options");
}

export function verifyLogin(credential: unknown): Promise<VerifyResponse> {
	return authPost("/login/verify", { credential });
}

/**
 * Logout: revoke the session token server-side.
 */
export async function logout(): Promise<void> {
	const { post } = await import("@/shared/api");
	await post("/api/account/logout");
}

/**
 * Refresh the session token before it expires.
 */
export async function refreshToken(): Promise<string | null> {
	const token = getSessionToken();
	if (!token) return null;
	try {
		const { post } = await import("@/shared/api");
		const data = await post<{ token: string }>("/api/account/refresh");
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
	return get<CredentialInfo[]>("/api/account/credentials");
}

/**
 * Delete a passkey by credential ID.
 */
export async function deleteCredential(credentialId: string): Promise<void> {
	const { del } = await import("@/shared/api");
	await del(`/api/account/credentials/${encodeURIComponent(credentialId)}`);
}

/**
 * Get current user info.
 */
export async function getCurrentUser(): Promise<UserInfo> {
	const { get } = await import("@/shared/api");
	return get<UserInfo>("/api/account/me");
}
