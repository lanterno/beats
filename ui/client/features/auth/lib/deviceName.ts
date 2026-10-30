/**
 * What a passkey is called in the list in Settings → Passkeys.
 *
 * A guess from the user agent, and nothing more: the browser does not say
 * which authenticator answered, so "Mac" means the browser that enrolled it,
 * not the key. It exists so two passkeys on one account can be told apart
 * well enough to remove the right one; where it cannot tell, the date beside
 * it can.
 *
 * iPhone and iPad are tested before Mac, not after: an iOS user agent ends
 * "like Mac OS X", so every iPhone passkey registered before this was called
 * "Mac".
 */
export function deviceName(): string {
	const ua = navigator.userAgent;
	if (ua.includes("iPhone")) return "iPhone";
	if (ua.includes("iPad")) return "iPad";
	if (ua.includes("Android")) return "Android";
	if (ua.includes("Mac")) return "Mac";
	if (ua.includes("Windows")) return "Windows PC";
	if (ua.includes("Linux")) return "Linux";
	return "Unknown Device";
}
