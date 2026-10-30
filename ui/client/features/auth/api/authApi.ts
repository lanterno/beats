/**
 * Auth API Client
 * Handles WebAuthn registration and authentication API calls.
 */
import type {
	PublicKeyCredentialCreationOptionsJSON,
	PublicKeyCredentialRequestOptionsJSON,
} from "@simplewebauthn/browser";
import { config } from "@/shared/config";
import { deviceName } from "../lib/deviceName";
import { getSessionToken } from "../stores/authStore";

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
	identities: LinkedIdentity[];
	/** True when a sign-in through a provider created this account. */
	sso_provisioned: boolean;
}

// Single sign-on (OpenID Connect)

export interface SSOProvider {
	id: string;
	name: string;
}

/** An identity at a provider that signs into this account. */
export interface LinkedIdentity {
	provider: string;
	/** The provider's name, or its id once the instance no longer offers it. */
	provider_name: string;
	name: string | null;
	email: string | null;
	linked_at: string;
}

export interface SSOStart {
	/** Where to send the browser. */
	authorize_url: string;
	/** Comes back on the callback; kept to check the callback is ours. */
	state: string;
}

export interface SSOComplete {
	intent: "sign_in" | "link";
	provider: string;
	/** A session token, for a sign-in; null for a link. */
	token: string | null;
	created: boolean;
}

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

// Single sign-on (OpenID Connect)
//
// The API keeps each sign-in's secrets; the browser keeps only its `state`,
// in sessionStorage, to check that a callback it receives is one this tab
// started. A link started from Settings goes the same way and is finished
// with the same session.

const SSO_STATE_KEY = "beats.sso.state";

/** The providers this instance offers. Never throws: none is an empty list. */
export async function getSsoProviders(): Promise<SSOProvider[]> {
	try {
		const response = await fetch(`${AUTH_BASE}/sso/providers`);
		if (!response.ok) return [];
		return (await response.json()).providers;
	} catch {
		return [];
	}
}

function goToProvider(started: SSOStart): void {
	sessionStorage.setItem(SSO_STATE_KEY, started.state);
	window.location.assign(started.authorize_url);
}

/** Leave for the provider's sign-in page. */
export async function startSsoSignIn(providerId: string): Promise<void> {
	const { post } = await import("@/shared/api");
	goToProvider(await post<SSOStart>(`/api/auth/sso/${encodeURIComponent(providerId)}/start`));
}

/** Leave for the provider to link an identity to the signed-in account. */
export async function startSsoLink(providerId: string): Promise<void> {
	const { post } = await import("@/shared/api");
	goToProvider(await post<SSOStart>(`/api/account/sso/${encodeURIComponent(providerId)}/link`));
}

/**
 * Whether `state` is the one this tab sent. Read once: the stored value is
 * removed either way, so a callback can't be replayed into this check.
 */
export function takeSsoState(state: string): boolean {
	const expected = sessionStorage.getItem(SSO_STATE_KEY);
	sessionStorage.removeItem(SSO_STATE_KEY);
	return expected !== null && expected === state;
}

/** Hand the provider's code to the API; sent with the session, if there is one. */
export async function completeSso(code: string, state: string): Promise<SSOComplete> {
	const { post } = await import("@/shared/api");
	return post<SSOComplete>("/api/auth/sso/complete", { code, state });
}

/** Detach the identity linked through a provider. */
export async function unlinkSsoIdentity(providerId: string): Promise<UserInfo> {
	const { del } = await import("@/shared/api");
	return del<UserInfo>(`/api/account/sso/${encodeURIComponent(providerId)}`);
}

export async function logout(): Promise<void> {
	const { post } = await import("@/shared/api");
	await post("/api/account/logout");
}

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

// Credential Management (authed endpoints — use centralized client)

export interface CredentialInfo {
	id: string;
	device_name: string | null;
	created_at: string;
}

export async function listCredentials(): Promise<CredentialInfo[]> {
	const { get } = await import("@/shared/api");
	return get<CredentialInfo[]>("/api/account/credentials");
}

/**
 * Put another passkey on this account, for this device.
 *
 * Not `/api/auth/register/*`: that is the sign-up door, and it answers 409
 * for an email that already has a passkey. So until #376 an account could
 * hold exactly one — no second device, and losing it locked the account out
 * unless single sign-on was linked. These two calls run the same ceremony
 * behind the session, so the account is the token's and no new token comes
 * back; the one in hand keeps working.
 *
 * The browser refuses to enrol an authenticator this account already holds
 * (the options' `excludeCredentials`), which surfaces as `InvalidStateError`
 * — a passkey already on this device, not a failure.
 */
export async function addPasskey(): Promise<void> {
	const [{ startRegistration }, { post }] = await Promise.all([
		import("@simplewebauthn/browser"),
		import("@/shared/api"),
	]);
	const { options } = await post<{ options: PublicKeyCredentialCreationOptionsJSON }>(
		"/api/account/credentials/start",
	);
	const credential = await startRegistration({ optionsJSON: options });
	// Nothing else on the account changes, so there is nothing to return;
	// the caller re-reads the list.
	await post("/api/account/credentials/verify", {
		credential,
		device_name: deviceName(),
	});
}

export async function deleteCredential(credentialId: string): Promise<void> {
	const { del } = await import("@/shared/api");
	await del(`/api/account/credentials/${encodeURIComponent(credentialId)}`);
}

export async function getCurrentUser(): Promise<UserInfo> {
	const { get } = await import("@/shared/api");
	return get<UserInfo>("/api/account/me");
}
