/**
 * Auth Feature
 *
 * Two independent ways into an account:
 * - WebAuthn/Passkey — Beats' own registration and login.
 * - home.space SSO — the optional federated door, hidden unless the API
 *   reports it enabled. Linking an existing account is done from Settings.
 */

// API
export type {
	CredentialInfo,
	SSOConfig,
	SSOLinkInfo,
	SSOSessionResponse,
	UserInfo,
} from "./api/authApi";
export {
	deleteCredential,
	getCurrentUser,
	getLoginOptions,
	getSsoConfig,
	linkSsoIdentity,
	listCredentials,
	logout,
	refreshToken,
	registerStart,
	ssoSignIn,
	unlinkSsoIdentity,
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
