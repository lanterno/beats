/**
 * Auth Feature
 * WebAuthn/Passkey authentication for the Beats app.
 */

// API
export type { CredentialInfo, UserInfo } from "./api/authApi";
export {
	deleteCredential,
	getCurrentUser,
	getLoginOptions,
	listCredentials,
	logout,
	refreshToken,
	registerStart,
	verifyLogin,
	verifyRegistration,
} from "./api/authApi";
// Components
export { default as AuthModal } from "./components/AuthModal";
export type { UserInfo as UserState } from "./stores/authStore";
// Store
export {
	clearSessionToken,
	getSessionToken,
	initializeAuth,
	isAuthenticated,
	setSessionToken,
	setUser,
	useAuth,
} from "./stores/authStore";
