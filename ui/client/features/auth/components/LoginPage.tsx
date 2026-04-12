/**
 * Login Page
 * Handles email-first registration and passkey authentication.
 */

import {
	browserSupportsWebAuthn,
	startAuthentication,
	startRegistration,
} from "@simplewebauthn/browser";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/shared/ui";
import {
	getLoginOptions,
	registerStart,
	verifyLogin,
	verifyRegistration,
} from "../api/authApi";
import { setSessionToken, useAuth } from "../stores/authStore";

type AuthMode = "register-email" | "register-passkey" | "login";

export default function LoginPage() {
	const navigate = useNavigate();
	const { isAuthenticated, isLoading: authLoading } = useAuth();

	const [mode, setMode] = useState<AuthMode>("login");
	const [error, setError] = useState<string | null>(null);
	const [isProcessing, setIsProcessing] = useState(false);
	const [webAuthnSupported, setWebAuthnSupported] = useState(true);

	// Registration state
	const [email, setEmail] = useState("");
	const [displayName, setDisplayName] = useState("");
	const [registrationOptions, setRegistrationOptions] = useState<Awaited<
		ReturnType<typeof registerStart>
	> | null>(null);

	// Check WebAuthn support on mount
	useEffect(() => {
		if (!browserSupportsWebAuthn()) {
			setWebAuthnSupported(false);
		}
	}, []);

	// Redirect if already authenticated
	useEffect(() => {
		if (isAuthenticated && !authLoading) {
			navigate("/app", { replace: true });
		}
	}, [isAuthenticated, authLoading, navigate]);

	const handleEmailSubmit = async (e: React.FormEvent) => {
		e.preventDefault();
		setError(null);
		setIsProcessing(true);

		try {
			const result = await registerStart(email, displayName || undefined);
			setRegistrationOptions(result);
			setMode("register-passkey");
		} catch (err) {
			if (err instanceof Error) {
				setError(err.message);
			} else {
				setError("Failed to start registration. Please try again.");
			}
		} finally {
			setIsProcessing(false);
		}
	};

	const handleRegisterPasskey = async () => {
		if (!registrationOptions) return;
		setError(null);
		setIsProcessing(true);

		try {
			const credential = await startRegistration({
				optionsJSON: registrationOptions.options,
			});

			const result = await verifyRegistration(credential, getDeviceName());

			if (result.verified) {
				setSessionToken(result.token);
				navigate("/app", { replace: true });
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
			const { options } = await getLoginOptions();
			const credential = await startAuthentication({ optionsJSON: options });
			const result = await verifyLogin(credential);

			if (result.verified) {
				setSessionToken(result.token);
				navigate("/app", { replace: true });
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

	if (authLoading) {
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
						<h1 className="text-2xl font-heading text-foreground mb-4">Browser Not Supported</h1>
						<p className="text-muted-foreground mb-6">
							Your browser does not support Passkeys/WebAuthn. Please use a modern browser like
							Chrome, Firefox, Safari, or Edge.
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
						<h1 className="font-heading text-3xl text-foreground tracking-tight">Beats</h1>
						<p className="mt-2 text-muted-foreground">
							{mode === "register-email" && "Create your account"}
							{mode === "register-passkey" && "Set up your passkey"}
							{mode === "login" && "Sign in with your passkey"}
						</p>
					</div>

					{/* Error message */}
					{error && (
						<div className="mb-6 p-4 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
							{error}
						</div>
					)}

					{/* Register: email step */}
					{mode === "register-email" && (
						<form onSubmit={handleEmailSubmit} className="space-y-4">
							<div>
								<label htmlFor="email" className="block text-sm font-medium text-foreground mb-1.5">
									Email
								</label>
								<input
									id="email"
									type="email"
									required
									value={email}
									onChange={(e) => setEmail(e.target.value)}
									placeholder="you@example.com"
									className="w-full rounded-md border border-input bg-background py-2.5 px-3 text-foreground placeholder:text-muted-foreground focus:outline-hidden focus:ring-2 focus:ring-accent/20 focus:border-accent/40"
									autoFocus
								/>
							</div>
							<div>
								<label
									htmlFor="displayName"
									className="block text-sm font-medium text-foreground mb-1.5"
								>
									Display name <span className="text-muted-foreground font-normal">(optional)</span>
								</label>
								<input
									id="displayName"
									type="text"
									value={displayName}
									onChange={(e) => setDisplayName(e.target.value)}
									placeholder="Your name"
									className="w-full rounded-md border border-input bg-background py-2.5 px-3 text-foreground placeholder:text-muted-foreground focus:outline-hidden focus:ring-2 focus:ring-accent/20 focus:border-accent/40"
								/>
							</div>
							<Button type="submit" className="w-full" size="lg" disabled={isProcessing || !email}>
								{isProcessing ? "Creating account..." : "Continue"}
							</Button>
						</form>
					)}

					{/* Register: passkey step */}
					{mode === "register-passkey" && (
						<div className="space-y-4">
							<p className="text-sm text-muted-foreground text-center">
								Account created for <span className="text-foreground font-medium">{email}</span>.
								Now set up your passkey.
							</p>
							<Button
								className="w-full"
								size="lg"
								onClick={handleRegisterPasskey}
								disabled={isProcessing}
							>
								{isProcessing ? "Setting up..." : "Set Up Passkey"}
							</Button>
							<p className="text-xs text-muted-foreground text-center">
								You'll use your device's biometrics (Face ID, Touch ID, Windows Hello, etc.) to sign
								in securely.
							</p>
						</div>
					)}

					{/* Login */}
					{mode === "login" && (
						<div className="space-y-4">
							<Button className="w-full" size="lg" onClick={handleLogin} disabled={isProcessing}>
								{isProcessing ? "Authenticating..." : "Sign In with Passkey"}
							</Button>
							<p className="text-xs text-muted-foreground text-center">
								Use your registered passkey to sign in.
							</p>
						</div>
					)}

					{/* Mode switch */}
					<div className="mt-8 pt-6 border-t border-border">
						{mode === "login" && (
							<button
								className="text-xs text-muted-foreground hover:text-foreground transition-colors w-full text-center"
								onClick={() => setMode("register-email")}
								disabled={isProcessing}
							>
								Create an account
							</button>
						)}
						{(mode === "register-email" || mode === "register-passkey") && (
							<button
								className="text-xs text-muted-foreground hover:text-foreground transition-colors w-full text-center"
								onClick={() => {
									setMode("login");
									setRegistrationOptions(null);
								}}
								disabled={isProcessing}
							>
								Already have a passkey? Sign in
							</button>
						)}
					</div>
				</div>
			</div>
		</div>
	);
}
