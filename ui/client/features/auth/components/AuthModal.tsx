import {
	browserSupportsWebAuthn,
	startAuthentication,
	startRegistration,
} from "@simplewebauthn/browser";
import { KeyRound, X } from "lucide-react";
import { type SyntheticEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { describeError } from "@/shared/api";
import { APP_NAME } from "@/shared/config";
import { BrandMark, Button } from "@/shared/ui";
import {
	getCurrentUser,
	getLoginOptions,
	getSsoProviders,
	registerStart,
	type SSOProvider,
	startSsoSignIn,
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

	const [providers, setProviders] = useState<SSOProvider[]>([]);

	// Single sign-on — the second door. Leaves for the provider; the way back
	// is `/auth/callback` (SsoCallbackPage), not this dialog.
	const handleSsoClick = async (provider: SSOProvider) => {
		setError(null);
		setIsProcessing(true);
		try {
			await startSsoSignIn(provider.id);
		} catch (err) {
			setError(describeError(err, `Couldn't reach ${provider.name}. Try again shortly.`));
			setIsProcessing(false);
		}
	};

	useEffect(() => {
		if (!browserSupportsWebAuthn()) {
			setWebAuthnSupported(false);
		}
	}, []);

	// The providers this instance offers: none, on most, and then no buttons.
	useEffect(() => {
		if (!open) return;
		let cancelled = false;
		getSsoProviders().then((list) => {
			if (!cancelled) setProviders(list);
		});
		return () => {
			cancelled = true;
		};
	}, [open]);

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
		<div className="fixed inset-0 z-50 flex items-center justify-center">
			<button
				type="button"
				aria-label="Close"
				tabIndex={-1}
				disabled={isProcessing}
				className="absolute inset-0 w-full bg-veil backdrop-blur-sm"
				onClick={onClose}
			/>
			<div className="relative w-full max-w-md mx-6 rounded-[1.75rem] bg-card p-8 shadow-card animate-in fade-in zoom-in-95 duration-200">
				{/* Close button */}
				<button
					type="button"
					aria-label="Close dialog"
					onClick={onClose}
					disabled={isProcessing}
					className="absolute top-4 right-4 grid place-items-center w-8 h-8 rounded-full text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
				>
					<X size={18} />
				</button>

				{!webAuthnSupported ? (
					<div className="text-center">
						<h2 className="text-2xl font-heading font-extrabold text-foreground mb-4">
							Browser Not Supported
						</h2>
						<p className="text-muted-foreground">
							Your browser does not support Passkeys/WebAuthn. Please use a modern browser like
							Chrome, Firefox, Safari, or Edge.
						</p>
					</div>
				) : (
					<>
						{/* Header */}
						<div className="text-center mb-8">
							<BrandMark className="w-14 h-14 mx-auto mb-4" />
							<h2 className="font-heading text-3xl font-extrabold text-foreground tracking-[-0.01em]">
								{APP_NAME}
							</h2>
							<p className="mt-2 font-medium text-muted-foreground">
								{mode === "register-email" && "Create your account"}
								{mode === "register-passkey" && "Set up your passkey"}
								{mode === "login" && "Sign in with your passkey"}
							</p>
						</div>

						{/* Error message */}
						{error && (
							<div className="mb-6 px-4 py-3 rounded-[1.125rem] bg-destructive/10 text-destructive-ink text-sm font-medium">
								{error}
							</div>
						)}

						{/* Register: email step */}
						{mode === "register-email" && (
							<form onSubmit={handleEmailSubmit} className="space-y-4">
								<div>
									<label
										htmlFor="auth-email"
										className="block font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground mb-[5px]"
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
										className="w-full rounded-xl bg-secondary py-2.5 px-3 text-foreground placeholder:text-muted-foreground focus:outline-hidden focus:ring-[3px] focus:ring-accent"
										autoFocus
									/>
								</div>
								<div>
									<label
										htmlFor="auth-displayName"
										className="block font-body text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted-foreground mb-[5px]"
									>
										Display name{" "}
										<span className="normal-case tracking-normal font-medium">(optional)</span>
									</label>
									<input
										id="auth-displayName"
										type="text"
										value={displayName}
										onChange={(e) => setDisplayName(e.target.value)}
										placeholder="Your name"
										className="w-full rounded-xl bg-secondary py-2.5 px-3 text-foreground placeholder:text-muted-foreground focus:outline-hidden focus:ring-[3px] focus:ring-accent"
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

						{/* Single sign-on — offered alongside, never instead of, the
						    passkey login above. Absent when no provider is set up. */}
						{providers.length > 0 && (mode === "login" || mode === "register-email") && (
							<div className="mt-6">
								<div className="flex items-center gap-3 mb-4">
									<span className="h-px flex-1 bg-border" />
									<span className="text-[10.5px] font-bold text-muted-foreground uppercase tracking-[0.14em]">
										or
									</span>
									<span className="h-px flex-1 bg-border" />
								</div>
								<div className="space-y-2">
									{providers.map((provider) => (
										<Button
											key={provider.id}
											type="button"
											variant="outline"
											className="w-full"
											size="lg"
											onClick={() => void handleSsoClick(provider)}
											disabled={isProcessing}
										>
											<KeyRound size={16} />
											Continue with {provider.name}
										</Button>
									))}
								</div>
							</div>
						)}

						{/* Mode switch */}
						<div className="mt-8 pt-6 border-t border-border">
							{mode === "login" && (
								<button
									type="button"
									className="text-[12.5px] font-bold text-muted-foreground hover:text-foreground transition-colors w-full text-center rounded-full focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
									onClick={() => setMode("register-email")}
									disabled={isProcessing}
								>
									Create an account
								</button>
							)}
							{(mode === "register-email" || mode === "register-passkey") && (
								<button
									type="button"
									className="text-[12.5px] font-bold text-muted-foreground hover:text-foreground transition-colors w-full text-center rounded-full focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
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
