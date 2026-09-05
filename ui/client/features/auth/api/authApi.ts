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
	sso: SSOLinkInfo;
}

// ============================================================================
// home.space SSO
// ============================================================================

export interface SSOConfig {
	enabled: boolean;
	provider_name: string;
	/** Where to send the browser for a home.space session. "" when it could
	 *  not be derived (a bare localhost) — the button stays hidden then. */
	login_url: string;
	/** Whether the browser already carries a Home-Session cookie. */
	session_present: boolean;
}

export interface SSOLinkInfo {
	linked: boolean;
	provider_name: string;
	did: string | null;
	holder_name: string | null;
	roles: string[];
	linked_at: string | null;
	provisioned: boolean;
}

export interface SSOSessionResponse {
	verified: boolean;
	token: string;
	created: boolean;
	did: string;
	holder_name: string;
	roles: string[];
	display_name: string | null;
	/** "issuer" when revocation was checked, "offline" when auth.home.space
	 *  was unreachable and only the signature could be verified. */
	verified_by: "issuer" | "offline";
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

// ============================================================================
// home.space SSO
//
// Every call here sends cookies. The `Home-Session` cookie is scoped to
// `.home.space`, so on the home deployment (where the SPA and the API share
// an origin) it rides along automatically — but `credentials: "include"`
// keeps this working when the two are split across ports in development.
// ============================================================================

/**
 * Whether this instance offers home.space SSO, and where to go for it.
 * Never throws: the login screen calls it on every load, and a deployment
 * without SSO should render exactly as it always did.
 */
export async function getSsoConfig(): Promise<SSOConfig> {
	const disabled: SSOConfig = {
		enabled: false,
		provider_name: "",
		login_url: "",
		session_present: false,
	};
	try {
		const response = await fetch(`${AUTH_BASE}/sso/config`, { credentials: "include" });
		if (!response.ok) return disabled;
		return await response.json();
	} catch {
		return disabled;
	}
}

/**
 * Exchange the browser's home.space session for a beats session token.
 * Throws an ApiError-shaped Error carrying `code` so the caller can tell
 * "no session yet" (redirect) from "not allowed" (explain).
 */
export async function ssoSignIn(): Promise<SSOSessionResponse> {
	const response = await fetch(`${AUTH_BASE}/sso/session`, {
		method: "POST",
		credentials: "include",
	});
	if (!response.ok) {
		const body = await response.json().catch(() => ({}));
		const error = new Error(body.detail || "home.space sign-in failed") as Error & {
			code?: string;
			status?: number;
		};
		error.code = body.code;
		error.status = response.status;
		throw error;
	}
	return response.json();
}

/**
 * Attach the browser's home.space identity to the signed-in beats account.
 * Requires both a beats session token and a Home-Session cookie.
 */
export async function linkSsoIdentity(): Promise<UserInfo> {
	const { post } = await import("@/shared/api");
	return post<UserInfo>("/api/account/sso/link");
}

/** Detach the linked home.space identity. */
export async function unlinkSsoIdentity(): Promise<UserInfo> {
	const { del } = await import("@/shared/api");
	return del<UserInfo>("/api/account/sso/link");
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
