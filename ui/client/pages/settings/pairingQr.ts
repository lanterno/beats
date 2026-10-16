import { isLoopbackUrl } from "@/shared/config";

/**
 * What the pairing QR in Settings → Daemon holds.
 *
 * The reader is the companion: `parseQrPairingPayload` in
 * `companion/lib/services/qr_pairing.dart` takes `code` and `api` from this
 * JSON and pairs against that API. `web` is the web app's address, so the
 * phone's links open the site that made the code. The test beside this file
 * pins the exact string, and the companion's `qr_pairing_test.dart` should
 * parse that same literal.
 *
 * A page opened at a loopback origin (the dev server, a local build pointed
 * at a remote API) leaves `web` out: that address is this machine, and a
 * phone that saved it would have links that open nothing. The QR still
 * pairs, because `api` is what the exchange needs.
 */
export interface PairingQr {
	/** The pairing code exactly as the API returned it. The exchange is case-sensitive. */
	code: string;
	/** The API's public base, as `publicApiBase` gives it. */
	api: string;
	/** The web app's origin. Left out of the payload when it is loopback. */
	web: string;
}

export function pairingQrPayload({ code, api, web }: PairingQr): string {
	return JSON.stringify(isLoopbackUrl(web) ? { code, api } : { code, api, web });
}
