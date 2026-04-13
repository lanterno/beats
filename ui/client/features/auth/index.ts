/**
 * Auth Feature
 * WebAuthn/Passkey authentication for the Beats app.
 */

export type { UserInfo } from "./api/authApi";
// API
export type { CredentialInfo } from "./api/authApi";
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
export { default as LoginPage } from "./components/LoginPage";
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
