/**
 * Auth Feature
 *
 * Two independent ways into an account:
 * - WebAuthn/Passkey — Beats' own registration and login.
 * - Single sign-on through OpenID Connect providers — one button per provider
 *   the API offers, none when it offers none. Linking an identity to an
 *   existing account is done from Settings; both come back to `/auth/callback`.
 */

// API
export type {
	CredentialInfo,
	LinkedIdentity,
	SSOComplete,
	SSOProvider,
	UserInfo,
} from "./api/authApi";
export {
	completeSso,
	deleteCredential,
	getCurrentUser,
	getLoginOptions,
	getSsoProviders,
	listCredentials,
	logout,
	refreshToken,
	registerStart,
	startSsoLink,
	startSsoSignIn,
	takeSsoState,
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
	getAuthUserKey,
	getSessionToken,
	initializeAuth,
	isAuthenticated,
	setSessionToken,
	setUser,
	subscribeToAuth,
	useAuth,
} from "./stores/authStore";
