/**
 * Where every single sign-on provider sends the browser back
 * (`OIDC_REDIRECT_URI`). Hands the code to the API and moves on: a sign-in
 * to the app, a link to Settings. On failure it says why and offers the way
 * back, rather than dropping someone on a blank page with a code in the URL.
 */

import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";
import {
	completeSso,
	getCurrentUser,
	setSessionToken,
	setUser,
	takeSsoState,
	useAuth,
} from "@/features/auth";
import { describeError } from "@/shared/api";
import { Button } from "@/shared/ui";

export default function SsoCallback() {
	const navigate = useNavigate();
	const { isAuthenticated } = useAuth();
	const [failure, setFailure] = useState<string | null>(null);
	// One attempt: the API spends the state on the first, and a second
	// (StrictMode's double effect, a re-render) would only report it spent.
	const handled = useRef(false);

	useEffect(() => {
		if (handled.current) return;
		handled.current = true;

		const params = new URLSearchParams(window.location.search);
		// The code is single-use, but it has no business in the history either.
		window.history.replaceState({}, "", window.location.pathname);

		const providerError = params.get("error");
		if (providerError) {
			takeSsoState(params.get("state") ?? "");
			setFailure(
				providerError === "access_denied"
					? "Sign-in was cancelled."
					: params.get("error_description") || `The provider refused (${providerError}).`,
			);
			return;
		}

		const code = params.get("code");
		const state = params.get("state");
		// Only a callback this tab started is finished. Anything else is a
		// link someone else made — finishing it would sign this browser into
		// their account.
		if (!code || !state || !takeSsoState(state)) {
			setFailure("This sign-in wasn't started here, or has already finished. Start again.");
			return;
		}

		completeSso(code, state)
			.then((result) => {
				if (result.intent === "link") {
					toast.success("Identity linked");
					navigate("/settings", { replace: true });
					return;
				}
				if (!result.token) throw new Error("The sign-in returned no session.");
				setSessionToken(result.token);
				getCurrentUser()
					.then((u) => setUser({ email: u.email, displayName: u.display_name }))
					.catch(() => {});
				navigate("/app", { replace: true });
			})
			.catch((err) => setFailure(describeError(err, "Sign-in failed. Start again.")));
	}, [navigate]);

	return (
		<div className="min-h-screen bg-background flex items-center justify-center">
			<div className="text-center px-6 max-w-sm" aria-live="polite">
				{failure ? (
					<>
						<p className="text-base font-medium text-foreground">{failure}</p>
						<Button asChild className="mt-8">
							<Link to={isAuthenticated ? "/settings" : "/"} replace>
								{isAuthenticated ? "Back to Settings" : "Back to sign in"}
							</Link>
						</Button>
					</>
				) : (
					<p className="text-muted-foreground">Signing you in…</p>
				)}
			</div>
		</div>
	);
}
