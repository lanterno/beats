/**
 * Auth Store
 * Manages authentication state, session tokens, and user info.
 * Uses localStorage for token persistence across browser sessions.
 */
import { useSyncExternalStore } from "react";

// ============================================================================
// Constants
// ============================================================================

const SESSION_TOKEN_KEY = "beats_session_token";

// Buffer in seconds — treat token as expired this many seconds early so
// in-flight requests don't race against the actual expiry.
const EXPIRY_BUFFER_SECONDS = 60;

/**
 * Decode a JWT payload without signature verification.
 * Returns null if the token is malformed.
 */
function decodeJwtPayload(token: string): { exp?: number; sub?: string } | null {
	try {
		const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
		return JSON.parse(atob(base64));
	} catch {
		return null;
	}
}

/**
 * Check if a JWT token is expired (or will expire within the buffer window).
 */
function isTokenExpired(token: string): boolean {
	const payload = decodeJwtPayload(token);
	if (!payload?.exp) return true;
	return Date.now() / 1000 > payload.exp - EXPIRY_BUFFER_SECONDS;
}

// ============================================================================
// State
// ============================================================================

export interface UserInfo {
	email: string;
	displayName: string | null;
}

interface AuthState {
	token: string | null;
	isAuthenticated: boolean;
	isLoading: boolean;
	user: UserInfo | null;
}

let state: AuthState = {
	token: null,
	isAuthenticated: false,
	isLoading: true,
	user: null,
};

// Auto-refresh timer handle
let refreshTimer: ReturnType<typeof setTimeout> | null = null;

// Subscribers for React's useSyncExternalStore
const listeners = new Set<() => void>();

function emitChange() {
	for (const listener of listeners) {
		listener();
	}
}

// ============================================================================
// Token Auto-Refresh
// ============================================================================

/**
 * Schedule a token refresh 5 minutes before expiry.
 * If the token has less than 5 minutes left, refresh immediately.
 */
function scheduleRefresh(token: string): void {
	if (refreshTimer) clearTimeout(refreshTimer);

	const payload = decodeJwtPayload(token);
	if (!payload?.exp) return;

	// Refresh 5 minutes before expiry
	const refreshAt = payload.exp - 5 * 60;
	const delayMs = Math.max(0, (refreshAt - Date.now() / 1000) * 1000);

	refreshTimer = setTimeout(async () => {
		try {
			const { refreshToken } = await import("../api/authApi");
			const newToken = await refreshToken();
			if (newToken) {
				setSessionToken(newToken);
			} else {
				clearSessionToken();
			}
		} catch {
			clearSessionToken();
		}
	}, delayMs);
}

function cancelRefresh(): void {
	if (refreshTimer) {
		clearTimeout(refreshTimer);
		refreshTimer = null;
	}
}

/**
 * On window focus, check if the token is near expiry and refresh proactively.
 * This handles cases where the user was away and the scheduled refresh missed.
 */
if (typeof document !== "undefined") {
	document.addEventListener("visibilitychange", async () => {
		if (document.visibilityState !== "visible") return;
		if (!state.token || !state.isAuthenticated) return;

		const payload = decodeJwtPayload(state.token);
		if (!payload?.exp) return;

		// Refresh if token expires within 5 minutes (the scheduled refresh may have missed)
		const timeLeft = payload.exp - Date.now() / 1000;
		if (timeLeft > 5 * 60) return;

		// Token near expiry or expired — try to refresh
		try {
			const { refreshToken } = await import("../api/authApi");
			const newToken = await refreshToken();
			if (newToken) {
				setSessionToken(newToken);
			} else {
				clearSessionToken();
			}
		} catch {
			clearSessionToken();
		}
	});
}

// ============================================================================
// Actions
// ============================================================================

/**
 * Initialize the auth store from localStorage.
 * If a token exists, fetches user info from the API.
 */
export async function initializeAuth(): Promise<void> {
	const storedToken = localStorage.getItem(SESSION_TOKEN_KEY);
	if (storedToken && !isTokenExpired(storedToken)) {
		state = {
			token: storedToken,
			isAuthenticated: true,
			isLoading: false,
			user: null,
		};
		emitChange();
		scheduleRefresh(storedToken);

		// Fetch user info in the background
		try {
			const { getCurrentUser } = await import("../api/authApi");
			const userInfo = await getCurrentUser();
			state = {
				...state,
				user: { email: userInfo.email, displayName: userInfo.display_name },
			};
			emitChange();
		} catch {
			// Token might be expired -- clear it
			clearSessionToken();
		}
	} else {
		if (storedToken) localStorage.removeItem(SESSION_TOKEN_KEY);
		state = {
			token: null,
			isAuthenticated: false,
			isLoading: false,
			user: null,
		};
		emitChange();
	}
}

/**
 * Set the session token after successful login/registration.
 */
export function setSessionToken(token: string): void {
	localStorage.setItem(SESSION_TOKEN_KEY, token);
	state = {
		...state,
		token,
		isAuthenticated: true,
		isLoading: false,
	};
	emitChange();
	scheduleRefresh(token);
}

/**
 * Set user info after fetching from API.
 */
export function setUser(user: UserInfo): void {
	state = { ...state, user };
	emitChange();
}

/**
 * Clear the session token (logout).
 */
export function clearSessionToken(): void {
	cancelRefresh();
	localStorage.removeItem(SESSION_TOKEN_KEY);
	state = {
		token: null,
		isAuthenticated: false,
		isLoading: false,
		user: null,
	};
	emitChange();
}

/**
 * Get the current session token.
 */
export function getSessionToken(): string | null {
	if (state.token && isTokenExpired(state.token)) {
		clearSessionToken();
		return null;
	}
	return state.token;
}

/**
 * Check if the user is authenticated.
 */
export function isAuthenticated(): boolean {
	return state.isAuthenticated;
}

// ============================================================================
// React Hook
// ============================================================================

function subscribe(callback: () => void): () => void {
	listeners.add(callback);
	return () => listeners.delete(callback);
}

function getSnapshot(): AuthState {
	return state;
}

/**
 * React hook to access auth state.
 * Re-renders when auth state changes.
 */
export function useAuth(): AuthState {
	return useSyncExternalStore(subscribe, getSnapshot);
}
