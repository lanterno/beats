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

// Subscribers for React's useSyncExternalStore
const listeners = new Set<() => void>();

function emitChange() {
	for (const listener of listeners) {
		listener();
	}
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
	if (storedToken) {
		state = {
			token: storedToken,
			isAuthenticated: true,
			isLoading: false,
			user: null,
		};
		emitChange();

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
		token,
		isAuthenticated: true,
		isLoading: false,
		user: null,
	};
	emitChange();
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
