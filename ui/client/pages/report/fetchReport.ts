/**
 * The report page's one request: the token from the URL's fragment, POSTed
 * in a body to `/api/public/reports` (docs/billing.md, *Report links
 * (phase 1c)*). A bare `fetch`, never `apiClient`: that one attaches the
 * session, and on a 401 ends it and sends the browser to "/", which would
 * drop the fragment and sign a freelancer out of their own app for opening a
 * link. Here no credential is sent and no answer signs anyone out.
 */
import { config } from "@/shared/config";
import { type PublicReport, PublicReportSchema } from "@/shared/report";

/** The API's `TOKEN_SHAPE`: a malformed token is declined without a request. */
const TOKEN_SHAPE = /^lpr_[A-Za-z0-9_-]{43}$/;

export type ReportState =
	| { kind: "loading" }
	| { kind: "ready"; report: PublicReport }
	| { kind: "dead" }
	| { kind: "limited" }
	| { kind: "unreachable" };

/** The token in `location.hash`, or null when there is none worth asking about. */
export function tokenFromHash(hash: string): string | null {
	const token = hash.slice(1);
	return TOKEN_SHAPE.test(token) ? token : null;
}

export async function fetchReport(token: string, fetchImpl = fetch): Promise<ReportState> {
	let response: Response;
	try {
		response = await fetchImpl(`${config.apiBaseUrl}/api/public/reports`, {
			method: "POST",
			credentials: "omit",
			cache: "no-store",
			referrerPolicy: "no-referrer",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ token }),
		});
	} catch {
		return { kind: "unreachable" };
	}
	if (response.status === 404) return { kind: "dead" };
	if (response.status === 429) return { kind: "limited" };
	if (!response.ok) return { kind: "unreachable" };
	try {
		const parsed = PublicReportSchema.safeParse(await response.json());
		return parsed.success ? { kind: "ready", report: parsed.data } : { kind: "unreachable" };
	} catch {
		return { kind: "unreachable" };
	}
}
