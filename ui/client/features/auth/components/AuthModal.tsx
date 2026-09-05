import {
	browserSupportsWebAuthn,
	startAuthentication,
	startRegistration,
} from "@simplewebauthn/browser";
import { KeyRound, X } from "lucide-react";
import { type SyntheticEvent, useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { describeError } from "@/shared/api";
import { Button } from "@/shared/ui";
import {
	getCurrentUser,
	getLoginOptions,
	getSsoConfig,
	registerStart,
	type SSOConfig,
	ssoSignIn,
	verifyLogin,
	verifyRegistration,
} from "../api/authApi";
import { setSessionToken, setUser } from "../stores/authStore";

type AuthMode = "register-email" | "register-passkey" | "login";

interface AuthModalProps {
	open: boolean;
	onClose: () => void;
	initialMode?: "login" | "register-email";
}

export default function AuthModal({ open, onClose, initialMode = "login" }: AuthModalProps) {
	const navigate = useNavigate();

	const [mode, setMode] = useState<AuthMode>(initialMode);
	const [error, setError] = useState<string | null>(null);
	const [isProcessing, setIsProcessing] = useState(false);
	const [webAuthnSupported, setWebAuthnSupported] = useState(true);

	const [email, setEmail] = useState("");
	const [displayName, setDisplayName] = useState("");
	const [registrationOptions, setRegistrationOptions] = useState<Awaited<
		ReturnType<typeof registerStart>
	> | null>(null);

	const [sso, setSso] = useState<SSOConfig | null>(null);

	// ------------------------------------------------------------------
	// home.space SSO — the second door
	// ------------------------------------------------------------------

	// Guards the return-from-issuer exchange to exactly one attempt. Without
	// it, `completeSsoSignIn` being a fresh closure on every render makes the
	// callback effect re-fire each time it sets state — a redirect loop
	// dressed up as a dependency array.
	const ssoCallbackHandled = useRef(false);

	const ssoLoginUrl = sso?.login_url ?? "";
	const ssoProviderName = sso?.provider_name ?? "home.space";

	/** Send the browser to the identity service, asking it to come back here. */
	const redirectToIssuer = useCallback((loginUrl: string) => {
		const returnTo = `${window.location.origin}${window.location.pathname}?sso=callback`;
		window.location.href = `${loginUrl}/?return_to=${encodeURIComponent(returnTo)}`;
	}, []);

	/**
	 * Trade the Home-Session cookie for a beats session.
	 *
	 * `fromCallback` marks the attempt made on return from the issuer. It
	 * suppresses the redirect-on-missing-session, which would otherwise
	 * bounce the browser straight back to an issuer that just declined to
	 * give us a cookie — an infinite loop instead of an error message.
	 */
	const completeSsoSignIn = useCallback(
		async (fromCallback = true): Promise<void> => {
			setError(null);
			setIsProcessing(true);
			try {
				const result = await ssoSignIn();
				setSessionToken(result.token);
				getCurrentUser()
					.then((u) => setUser({ email: u.email, displayName: u.display_name }))
					.catch(() => {});
				navigate("/app", { replace: true });
			} catch (err) {
				const failure = err as Error & { code?: string };
				const needsIssuer =
					failure.code === "SSO_NO_SESSION" || failure.code === "SSO_INVALID_SESSION";
				if (needsIssuer && !fromCallback && ssoLoginUrl) {
					redirectToIssuer(ssoLoginUrl);
					return;
				}
				if (needsIssuer) {
					setError(`No active ${ssoProviderName} session. Sign in there, then try again.`);
				} else {
					setError(failure.message || "Sign-in failed. Please try again.");
				}
			} finally {
				setIsProcessing(false);
			}
		},
		[navigate, redirectToIssuer, ssoLoginUrl, ssoProviderName],
	);

	const handleSsoClick = () => {
		if (!sso?.enabled) return;
		// A cookie is already here — try it before sending the user away.
		if (sso.session_present) {
			void completeSsoSignIn(false);
			return;
		}
		if (ssoLoginUrl) {
			redirectToIssuer(ssoLoginUrl);
			return;
		}
		void completeSsoSignIn(true);
	};

	useEffect(() => {
		if (!browserSupportsWebAuthn()) {
			setWebAuthnSupported(false);
		}
	}, []);

	// Ask the API whether this instance offers home.space SSO. It answers
	// "disabled" rather than erroring when it doesn't, so a deployment
	// without an identity service renders exactly as it always did.
	useEffect(() => {
		if (!open) return;
		let cancelled = false;
		getSsoConfig().then((cfg) => {
			if (!cancelled) setSso(cfg);
		});
		return () => {
			cancelled = true;
		};
	}, [open]);

	// Coming back from auth.home.space, which redirects to
	// `?sso=callback` once it has set the Home-Session cookie. Exchange it
	// straight away so the round trip looks like one click.
	useEffect(() => {
		if (!open || !sso?.enabled || ssoCallbackHandled.current) return;
		const params = new URLSearchParams(window.location.search);
		if (params.get("sso") !== "callback") return;
		ssoCallbackHandled.current = true;
		// Drop the marker too, so a failed exchange doesn't leave a URL that
		// re-triggers on the next reload.
		params.delete("sso");
		const query = params.toString();
		window.history.replaceState({}, "", window.location.pathname + (query ? `?${query}` : ""));
		void completeSsoSignIn(true);
	}, [open, sso?.enabled, completeSsoSignIn]);

	useEffect(() => {
		if (open) {
			setMode(initialMode);
			setError(null);
			setEmail("");
			setDisplayName("");
			setRegistrationOptions(null);
		}
	}, [open, initialMode]);

	useEffect(() => {
		if (!open) return;
		const handleKey = (e: KeyboardEvent) => {
			if (e.key === "Escape" && !isProcessing) onClose();
		};
		document.addEventListener("keydown", handleKey);
		return () => document.removeEventListener("keydown", handleKey);
	}, [open, isProcessing, onClose]);

	if (!open) return null;

	// The button needs somewhere to send the browser. An enabled instance
	// with no derivable login URL (a bare `localhost`, where there is no
	// `auth.` sibling) would render a button that goes nowhere.
	const ssoAvailable = Boolean(sso?.enabled && sso.login_url);

	const handleEmailSubmit = async (e: SyntheticEvent<HTMLFormElement>) => {
		e.preventDefault();
		setError(null);
		setIsProcessing(true);

		try {
			const result = await registerStart(email, displayName || undefined);
			setRegistrationOptions(result);
			setMode("register-passkey");
		} catch (err) {
			setError(describeError(err, "Failed to start registration. Please try again."));
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
				getCurrentUser()
					.then((u) => setUser({ email: u.email, displayName: u.display_name }))
					.catch(() => {});
				navigate("/app", { replace: true });
			} else {
				setError("Registration failed. Please try again.");
			}
		} catch (err) {
			// WebAuthn surfaces a user-cancellation as `NotAllowedError`
			// — keep the friendly "cancelled or timed out" copy for that
			// case rather than falling through to the API detail (which
			// is empty here anyway).
			if (err instanceof Error && err.name === "NotAllowedError") {
				setError("Registration was cancelled or timed out.");
			} else {
				setError(describeError(err, "Registration failed. Please try again."));
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
				getCurrentUser()
					.then((u) => setUser({ email: u.email, displayName: u.display_name }))
					.catch(() => {});
				navigate("/app", { replace: true });
			} else {
				setError("Authentication failed. Please try again.");
			}
		} catch (err) {
			// Same NotAllowedError-as-cancellation rule as register —
			// kept inline rather than extracted because the friendly
			// copy differs ("Authentication" vs "Registration").
			if (err instanceof Error && err.name === "NotAllowedError") {
				setError("Authentication was cancelled or timed out.");
			} else {
				setError(describeError(err, "Authentication failed. Please try again."));
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

	return (
		<div
			className="fixed inset-0 z-50 flex items-center justify-center"
			onClick={(e) => {
				if (e.target === e.currentTarget && !isProcessing) onClose();
			}}
		>
			<div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
			<div className="relative w-full max-w-md mx-6 bg-card border border-border rounded-lg p-8 shadow-soft animate-in fade-in zoom-in-95 duration-200">
				{/* Close button */}
				<button
					onClick={onClose}
					disabled={isProcessing}
					className="absolute top-4 right-4 text-muted-foreground hover:text-foreground transition-colors"
				>
					<X size={18} />
				</button>

				{!webAuthnSupported ? (
					<div className="text-center">
						<h2 className="text-2xl font-heading text-foreground mb-4">Browser Not Supported</h2>
						<p className="text-muted-foreground">
							Your browser does not support Passkeys/WebAuthn. Please use a modern browser like
							Chrome, Firefox, Safari, or Edge.
						</p>
					</div>
				) : (
					<>
						{/* Header */}
						<div className="text-center mb-8">
							<h2 className="font-heading text-3xl text-foreground tracking-tight">Beats</h2>
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
									<label
										htmlFor="auth-email"
										className="block text-sm font-medium text-foreground mb-1.5"
									>
										Email
									</label>
									<input
										id="auth-email"
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
										htmlFor="auth-displayName"
										className="block text-sm font-medium text-foreground mb-1.5"
									>
										Display name{" "}
										<span className="text-muted-foreground font-normal">(optional)</span>
									</label>
									<input
										id="auth-displayName"
										type="text"
										value={displayName}
										onChange={(e) => setDisplayName(e.target.value)}
										placeholder="Your name"
										className="w-full rounded-md border border-input bg-background py-2.5 px-3 text-foreground placeholder:text-muted-foreground focus:outline-hidden focus:ring-2 focus:ring-accent/20 focus:border-accent/40"
									/>
								</div>
								<Button
									type="submit"
									className="w-full"
									size="lg"
									disabled={isProcessing || !email}
								>
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
									You'll use your device's biometrics (Face ID, Touch ID, Windows Hello, etc.) to
									sign in securely.
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

						{/* home.space SSO — offered alongside, never instead of, the
						    passkey login above. Hidden entirely when the instance
						    has no identity service configured. */}
						{ssoAvailable && (mode === "login" || mode === "register-email") && (
							<div className="mt-6">
								<div className="flex items-center gap-3 mb-4">
									<span className="h-px flex-1 bg-border" />
									<span className="text-xs text-muted-foreground uppercase tracking-wide">or</span>
									<span className="h-px flex-1 bg-border" />
								</div>
								<Button
									type="button"
									variant="outline"
									className="w-full"
									size="lg"
									onClick={handleSsoClick}
									disabled={isProcessing}
								>
									<KeyRound size={16} />
									Continue with {sso?.provider_name}
								</Button>
								<p className="mt-2 text-xs text-muted-foreground text-center">
									Use the identity you already have on {sso?.provider_name}.
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
					</>
				)}
			</div>
		</div>
	);
}
