/**
 * Report Link API Functions
 * Under /api/billing/report-links, outside every device-token prefix, as
 * all of billing is (docs/billing.md, phase 1c). The report a link opens is
 * read by the report page under /api/public, never from here; the preview
 * builds the same report for a scope before any link exists.
 */

import {
	ApiReportLinkCreatedSchema,
	ApiReportLinkListSchema,
	del,
	get,
	parseApiResponse,
	post,
	ReportLinksTurnedOffSchema,
} from "@/shared/api";
import { type PublicReport, PublicReportSchema } from "@/shared/report";
import type { ReportLink, ReportLinkInput, ReportLinkMade, ReportScopeInput } from "../model";
import { toApiReportLinkInput, toApiReportScope, toReportLink } from "../model";

/** The caller's links, one client's or every one, newest first, live and ended. */
export async function fetchReportLinks(clientId?: string): Promise<ReportLink[]> {
	const params = clientId ? `?${new URLSearchParams({ client_id: clientId }).toString()}` : "";
	const data = await get<unknown>(`/api/billing/report-links${params}`);
	return parseApiResponse(ApiReportLinkListSchema, data).map(toReportLink);
}

/**
 * Make a link, its days counted in `tz`. Answers with its token, once: the
 * API keeps only a hash of it, and nothing ever returns it again.
 *
 * A plain `post`, called from the dialog's click handler: never
 * `apiMutate`, whose offline queue would send it again after the dialog had
 * closed and make a link whose address nobody saw, and never a
 * `useMutation`, whose cache would hold the token after the dialog had gone
 * and whose default retry would make a second link on a lost answer. 404
 * CLIENT_NOT_FOUND, 409 PROJECT_NOT_BILLED_TO_CLIENT naming
 * `project_ids.N`, 409 RANGE_NOT_OVER, a 422 naming the key, 400
 * INVALID_TIMEZONE.
 */
export async function createReportLink(
	input: ReportLinkInput,
	tz: string,
): Promise<ReportLinkMade> {
	const params = new URLSearchParams({ tz });
	const data = await post<unknown>(
		`/api/billing/report-links?${params.toString()}`,
		toApiReportLinkInput(input),
	);
	const { token, ...link } = parseApiResponse(ApiReportLinkCreatedSchema, data);
	return { link: toReportLink(link), token };
}

/**
 * The report a link over `scope` would show, exactly as its client will
 * read it. Stores nothing, and is refused as the create is. A POST, so no
 * service worker's cache can hold it.
 */
export async function previewReport(scope: ReportScopeInput, tz: string): Promise<PublicReport> {
	const params = new URLSearchParams({ tz });
	const data = await post<unknown>(
		`/api/billing/report-links/preview?${params.toString()}`,
		toApiReportScope(scope),
	);
	return parseApiResponse(PublicReportSchema, data);
}

/** Turn a link off, or remove an ended one: it is deleted. 404 when it is already gone. */
export async function deleteReportLink(linkId: string): Promise<void> {
	await del<void>(`/api/billing/report-links/${linkId}`);
}

/** Turn off one client's links, or with null every one. How many were turned off. */
export async function turnOffReportLinks(clientId: string | null): Promise<number> {
	const data = await post<unknown>("/api/billing/report-links/turn-off", { client_id: clientId });
	return parseApiResponse(ReportLinksTurnedOffSchema, data).turned_off;
}
