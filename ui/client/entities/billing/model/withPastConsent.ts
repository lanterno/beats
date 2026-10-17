/**
 * Nothing retroactive without consent (docs/billing.md). A client's rates,
 * a project's billing and stopping it each carry a required `rewrite_past`;
 * the API answers 409 RETROACTIVE_CHANGE when the write would change the
 * figures of a month already over and `rewrite_past` is false, its `detail`
 * naming the first month touched. The consent is the server's to check: this
 * only asks the user, with the server's own words, and sends again.
 */

import { ApiError } from "@/shared/api";

const RETROACTIVE_CHANGE = "RETROACTIVE_CHANGE";

/**
 * Send with `rewritePast` false; on RETROACTIVE_CHANGE, ask `confirm` with
 * the API's `detail` and, if the user agrees, send again with it true.
 * Undefined when the user declines, so nothing was written. Any other
 * failure, the second send's included, is thrown as it came.
 */
export async function withPastConsent<T>(
	send: (rewritePast: boolean) => Promise<T>,
	confirm: (detail: string) => boolean | Promise<boolean>,
): Promise<T | undefined> {
	try {
		return await send(false);
	} catch (error) {
		if (!(error instanceof ApiError) || error.code !== RETROACTIVE_CHANGE) throw error;
		if (!(await confirm(error.message))) return undefined;
		return send(true);
	}
}
