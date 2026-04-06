/**
 * Auth API Client
 * Handles WebAuthn registration and authentication API calls.
 */
import type {
  PublicKeyCredentialCreationOptionsJSON,
  PublicKeyCredentialRequestOptionsJSON,
} from "@simplewebauthn/browser";
import { config } from "@/shared/config";

// ============================================================================
// Types
// ============================================================================

export interface AuthStatus {
  is_registered: boolean;
  credentials_count: number;
}

export interface RegistrationOptions {
  options: PublicKeyCredentialCreationOptionsJSON;
}

export interface LoginOptions {
  options: PublicKeyCredentialRequestOptionsJSON;
}

export interface VerifyResponse {
  verified: boolean;
  token: string;
}

// ============================================================================
// API Functions
// ============================================================================

const AUTH_BASE = `${config.apiBaseUrl}/api/auth`;

/**
 * Check if any passkeys are registered.
 */
export async function getAuthStatus(): Promise<AuthStatus> {
  const response = await fetch(`${AUTH_BASE}/status`);
  if (!response.ok) {
    throw new Error("Failed to get auth status");
  }
  return response.json();
}

/**
 * Get registration options from the server.
 */
export async function getRegistrationOptions(): Promise<RegistrationOptions> {
  const response = await fetch(`${AUTH_BASE}/register/options`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || "Failed to get registration options");
  }
  return response.json();
}

/**
 * Verify registration with the server.
 */
export async function verifyRegistration(
  credential: unknown,
  deviceName?: string
): Promise<VerifyResponse> {
  const response = await fetch(`${AUTH_BASE}/register/verify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      credential,
      device_name: deviceName,
    }),
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
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      credential,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || "Login verification failed");
  }
  return response.json();
}
