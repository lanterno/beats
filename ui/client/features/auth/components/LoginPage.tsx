/**
 * Login Page
 * Handles WebAuthn passkey registration and authentication.
 */
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  startRegistration,
  startAuthentication,
  browserSupportsWebAuthn,
} from "@simplewebauthn/browser";
import { Button } from "@/shared/ui";
import {
  getAuthStatus,
  getRegistrationOptions,
  verifyRegistration,
  getLoginOptions,
  verifyLogin,
} from "../api/authApi";
import { setSessionToken, useAuth } from "../stores/authStore";

type AuthMode = "loading" | "register" | "login";

export default function LoginPage() {
  const navigate = useNavigate();
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  const [mode, setMode] = useState<AuthMode>("loading");
  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [webAuthnSupported, setWebAuthnSupported] = useState(true);

  // Check WebAuthn support and auth status on mount
  useEffect(() => {
    const init = async () => {
      // Check browser support
      if (!browserSupportsWebAuthn()) {
        setWebAuthnSupported(false);
        setMode("login"); // Will show unsupported message
        return;
      }

      try {
        const status = await getAuthStatus();
        setMode(status.is_registered ? "login" : "register");
      } catch (err) {
        console.error("Failed to check auth status:", err);
        setError("Failed to connect to server. Please try again.");
        setMode("login");
      }
    };

    if (!authLoading) {
      init();
    }
  }, [authLoading]);

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated && !authLoading) {
      navigate("/", { replace: true });
    }
  }, [isAuthenticated, authLoading, navigate]);

  const handleRegister = async () => {
    setError(null);
    setIsProcessing(true);

    try {
      // Get registration options from server
      const { options } = await getRegistrationOptions();

      // Start WebAuthn registration ceremony
      const credential = await startRegistration({ optionsJSON: options });

      // Verify with server and get session token
      const result = await verifyRegistration(credential, getDeviceName());

      if (result.verified) {
        setSessionToken(result.token);
        navigate("/", { replace: true });
      } else {
        setError("Registration failed. Please try again.");
      }
    } catch (err) {
      console.error("Registration error:", err);
      if (err instanceof Error) {
        if (err.name === "NotAllowedError") {
          setError("Registration was cancelled or timed out.");
        } else {
          setError(err.message || "Registration failed. Please try again.");
        }
      } else {
        setError("Registration failed. Please try again.");
      }
    } finally {
      setIsProcessing(false);
    }
  };

  const handleLogin = async () => {
    setError(null);
    setIsProcessing(true);

    try {
      // Get login options from server
      const { options } = await getLoginOptions();

      // Start WebAuthn authentication ceremony
      const credential = await startAuthentication({ optionsJSON: options });

      // Verify with server and get session token
      const result = await verifyLogin(credential);

      if (result.verified) {
        setSessionToken(result.token);
        navigate("/", { replace: true });
      } else {
        setError("Authentication failed. Please try again.");
      }
    } catch (err) {
      console.error("Login error:", err);
      if (err instanceof Error) {
        if (err.name === "NotAllowedError") {
          setError("Authentication was cancelled or timed out.");
        } else {
          setError(err.message || "Authentication failed. Please try again.");
        }
      } else {
        setError("Authentication failed. Please try again.");
      }
    } finally {
      setIsProcessing(false);
    }
  };

  // Get a friendly device name
  const getDeviceName = (): string => {
    const ua = navigator.userAgent;
    if (ua.includes("Mac")) return "Mac";
    if (ua.includes("Windows")) return "Windows PC";
    if (ua.includes("iPhone")) return "iPhone";
    if (ua.includes("iPad")) return "iPad";
    if (ua.includes("Android")) return "Android";
    if (ua.includes("Linux")) return "Linux";
    return "Unknown Device";
  };

  if (authLoading || mode === "loading") {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    );
  }

  if (!webAuthnSupported) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-6">
        <div className="max-w-md w-full">
          <div className="bg-card border border-border rounded-lg p-8 shadow-soft text-center">
            <h1 className="text-2xl font-heading text-foreground mb-4">
              Browser Not Supported
            </h1>
            <p className="text-muted-foreground mb-6">
              Your browser does not support Passkeys/WebAuthn. Please use a modern
              browser like Chrome, Firefox, Safari, or Edge.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-6">
      <div className="max-w-md w-full">
        <div className="bg-card border border-border rounded-lg p-8 shadow-soft">
          {/* Header */}
          <div className="text-center mb-8">
            <h1 className="font-heading text-3xl text-foreground tracking-tight">
              Beats
            </h1>
            <p className="mt-2 text-muted-foreground">
              {mode === "register"
                ? "Set up your passkey to get started"
                : "Sign in with your passkey"}
            </p>
          </div>

          {/* Error message */}
          {error && (
            <div className="mb-6 p-4 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
              {error}
            </div>
          )}

          {/* Action button */}
          {mode === "register" ? (
            <div className="space-y-4">
              <Button
                className="w-full"
                size="lg"
                onClick={handleRegister}
                disabled={isProcessing}
              >
                {isProcessing ? "Setting up..." : "Set Up Passkey"}
              </Button>
              <p className="text-xs text-muted-foreground text-center">
                You'll use your device's biometrics (Face ID, Touch ID, Windows
                Hello, etc.) to sign in securely.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <Button
                className="w-full"
                size="lg"
                onClick={handleLogin}
                disabled={isProcessing}
              >
                {isProcessing ? "Authenticating..." : "Sign In with Passkey"}
              </Button>
              <p className="text-xs text-muted-foreground text-center">
                Use your registered passkey to sign in.
              </p>
            </div>
          )}

          {/* Mode switch (for testing/recovery) */}
          <div className="mt-8 pt-6 border-t border-border">
            <button
              className="text-xs text-muted-foreground hover:text-foreground transition-colors w-full text-center"
              onClick={() => setMode(mode === "register" ? "login" : "register")}
              disabled={isProcessing}
            >
              {mode === "register"
                ? "Already have a passkey? Sign in"
                : "Need to set up a passkey?"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
