/**
 * Report Link TanStack Query Hooks
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { reportLinksRootKey } from "@/shared/api";
import type { PublicReport } from "@/shared/report";
import type { ReportLink, ReportScopeInput } from "../model";
import {
	deleteReportLink,
	fetchReportLinks,
	previewReport,
	turnOffReportLinks,
} from "./reportLinkApi";

/**
 * Every key sits under `reportLinksRootKey`, which a billing write and a
 * client delete in other entities invalidate (`shared/api/keys.ts`): either
 * can take a project, or every link, away.
 */
export const reportLinkKeys = {
	all: reportLinksRootKey,
	list: (clientId?: string) => [...reportLinkKeys.all, "list", clientId ?? "all"] as const,
	preview: (scope: ReportScopeInput, tz: string) =>
		[...reportLinkKeys.all, "preview", tz, scope] as const,
};

/** The caller's links, one client's or every client's, live and ended. */
export function useReportLinks(clientId?: string, { enabled = true }: { enabled?: boolean } = {}) {
	return useQuery({
		queryKey: reportLinkKeys.list(clientId),
		queryFn: (): Promise<ReportLink[]> => fetchReportLinks(clientId),
		enabled,
	});
}

/**
 * The report a link over `scope` would show. Never fresh from the cache,
 * as the month's figures: it is what the freelancer checks before sending.
 * A refusal is an answer (a range not over, a project no longer billed), so
 * it is not retried; the last report stays on screen while the next loads.
 */
export function useReportPreview(
	scope: ReportScopeInput,
	tz: string,
	{ enabled = true }: { enabled?: boolean } = {},
) {
	return useQuery({
		queryKey: reportLinkKeys.preview(scope, tz),
		queryFn: (): Promise<PublicReport> => previewReport(scope, tz),
		staleTime: 0,
		retry: false,
		placeholderData: keepPreviousData,
		enabled,
	});
}

function useInvalidateReportLinks() {
	const queryClient = useQueryClient();
	return () => queryClient.invalidateQueries({ queryKey: reportLinkKeys.all });
}

/**
 * Turn a link off, or remove an ended one. Not retried: a second DELETE of a
 * link the first one took would answer 404.
 */
export function useDeleteReportLink() {
	const invalidate = useInvalidateReportLinks();
	return useMutation({
		mutationFn: (linkId: string) => deleteReportLink(linkId),
		onSuccess: invalidate,
		retry: 0,
	});
}

/** Turn off one client's links, or with null every one: Settings' way out of a stolen session. */
export function useTurnOffReportLinks() {
	const invalidate = useInvalidateReportLinks();
	return useMutation({
		mutationFn: (clientId: string | null) => turnOffReportLinks(clientId),
		onSuccess: invalidate,
		retry: 0,
	});
}
