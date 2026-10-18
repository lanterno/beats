/**
 * Report Link Entity - public API
 *
 * The links a client opens their report with, no sign-in needed
 * (docs/billing.md, phase 1c): made for one client, some of its billed
 * projects and a stretch of finished days, shown once, listed without their
 * token, and turned off by deleting them. The report a link shows is drawn
 * by `widgets/client-report` from `shared/report`'s schema.
 */
export {
	createReportLink,
	deleteReportLink,
	useDeleteReportLink,
	useReportLinks,
	useReportPreview,
	useTurnOffReportLinks,
} from "./api";
export {
	describeShows,
	type ExpiryChoice,
	expiryFor,
	notOnLink,
	type RangeChoice,
	type ReportLink,
	type ReportLinkInput,
	type ReportLinkMade,
	type ReportLinkProject,
	type ReportScopeInput,
	rangeFor,
	reportUrl,
	TURN_OFF_QUESTION,
	todayIn,
} from "./model";
export { ReportLinkRow, type ReportLinkRowProps } from "./ui";
