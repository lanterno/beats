/**
 * Auth Store
 * Manages authentication state and session tokens.
 * Uses sessionStorage for token persistence within browser sessions.
 */
import { useSyncExternalStore } from "react";

// ============================================================================
// Constants
// ============================================================================

const SESSION_TOKEN_KEY = "beats_session_token";

// ============================================================================
// State
// ============================================================================

interface AuthState {
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

let state: AuthState = {
  token: null,
  isAuthenticated: false,
  isLoading: true,
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
 * Initialize the auth store from sessionStorage.
 * Call this on app startup.
 */
export function initializeAuth(): void {
  const storedToken = sessionStorage.getItem(SESSION_TOKEN_KEY);
  if (storedToken) {
    state = {
      token: storedToken,
      isAuthenticated: true,
      isLoading: false,
    };
  } else {
    state = {
      token: null,
      isAuthenticated: false,
      isLoading: false,
    };
  }
  emitChange();
}

/**
 * Set the session token after successful login/registration.
 */
export function setSessionToken(token: string): void {
  sessionStorage.setItem(SESSION_TOKEN_KEY, token);
  state = {
    token,
    isAuthenticated: true,
    isLoading: false,
  };
  emitChange();
}

/**
 * Clear the session token (logout).
 */
export function clearSessionToken(): void {
  sessionStorage.removeItem(SESSION_TOKEN_KEY);
  state = {
    token: null,
    isAuthenticated: false,
    isLoading: false,
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
