/**
 * Auth Feature
 * WebAuthn/Passkey authentication for the Beats app.
 */

// API
export {
	getAuthStatus,
	getLoginOptions,
	getRegistrationOptions,
	verifyLogin,
	verifyRegistration,
} from "./api/authApi";
// Components
export { default as LoginPage } from "./components/LoginPage";
// Store
export {
	clearSessionToken,
	getSessionToken,
	initializeAuth,
	isAuthenticated,
	setSessionToken,
	useAuth,
} from "./stores/authStore";
