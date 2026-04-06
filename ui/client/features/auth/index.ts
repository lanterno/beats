/**
 * Auth Feature
 * WebAuthn/Passkey authentication for the Beats app.
 */

// Components
export { default as LoginPage } from "./components/LoginPage";

// Store
export {
  useAuth,
  initializeAuth,
  setSessionToken,
  clearSessionToken,
  getSessionToken,
  isAuthenticated,
} from "./stores/authStore";

// API
export {
  getAuthStatus,
  getRegistrationOptions,
  verifyRegistration,
  getLoginOptions,
  verifyLogin,
} from "./api/authApi";
