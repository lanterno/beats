import type { ApiReportLink } from "@/shared/api";
import type { ReportLink, ReportLinkInput, ReportScopeInput } from "./types";

export function toReportLink(api: ApiReportLink): ReportLink {
	return {
		id: api.id,
		clientId: api.client_id,
		label: api.label ?? undefined,
		first: api.first,
		last: api.last,
		tz: api.tz,
		showAmounts: api.show_amounts,
		showNotes: api.show_notes,
		projects: api.projects.map((project) => ({ id: project.id, name: project.name })),
		expiresOn: api.expires_on,
		createdAt: api.created_at,
		state: api.state,
	};
}

/** The preview's body. Every key is sent: the API requires each. */
export function toApiReportScope(scope: ReportScopeInput) {
	return {
		client_id: scope.clientId,
		project_ids: scope.projectIds,
		first: scope.first,
		last: scope.last,
		show_amounts: scope.showAmounts,
		show_notes: scope.showNotes,
	};
}

/** The create's body: the scope, the label (null without one) and the last day. */
export function toApiReportLinkInput(input: ReportLinkInput) {
	return {
		...toApiReportScope(input),
		label: input.label ?? null,
		expires_on: input.expiresOn,
	};
}
