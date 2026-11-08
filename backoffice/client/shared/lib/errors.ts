/**
 * What a failed request says to the operator: what to do about it, never a
 * raw exception. The API's own words are kept wherever they are already
 * plain ("An erasure is queued for this account; cancel the job instead");
 * this names only the failures whose detail is written for a log.
 */

import { OperatorApiError } from "@/shared/api/client";

const SIGNED_OUT = "Your Google sign-in has lapsed. Reload the page to sign in again.";

const IN_PLAIN_WORDS: Record<string, string> = {
	NO_IAP_ASSERTION: SIGNED_OUT,
	IAP_REJECTED: SIGNED_OUT,
	IAP_UNAVAILABLE: "Google's sign-in check didn't answer. Try again in a moment.",
	OPERATOR_NOT_ALLOWED: "This Google account isn't on the operators' list.",
	// The run.app URL stays up behind the same IAP (docs/backoffice.md).
	OPERATOR_BAD_ORIGIN:
		"This address can read but can't change anything. Make the change from backoffice.lifepete.com.",
	CONFIRMATION_MISMATCH: "That doesn't match. Type it exactly as it's written on this page.",
	VIEWER_CANNOT_ACT: "Your role can read here, but it can't run commands.",
};

export function plainMessage(error: unknown): string {
	if (error instanceof OperatorApiError) {
		const plain = error.code ? IN_PLAIN_WORDS[error.code] : undefined;
		if (plain) return plain;
		return error.statusCode >= 500
			? "Something went wrong on the server. Try again in a moment."
			: error.message;
	}
	// fetch rejects when nothing answered, which is also what a lapsed IAP
	// session looks like: its redirect to Google is refused as cross-origin.
	return "Couldn't reach the server. Check your connection, then reload the page in case your sign-in has lapsed.";
}
