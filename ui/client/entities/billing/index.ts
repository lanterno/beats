/**
 * Billing Entity - public API
 *
 * A freelance project's billing — its client and dated terms, each saying
 * whether its hours are billable and at what rate — the marks that make one
 * entry billable or not against its term, and what a month comes to per
 * client (docs/billing.md), and the billing budgets on a client or a billed
 * project with how much of each is spent. Each lives in its own collection
 * under /api/billing, never on a project or an entry. The page never prices
 * anything: every amount is the API's.
 */
export {
	useBillableOverrides,
	useBillingBudgets,
	useBillingMonth,
	useClearEntryBillable,
	useCreateReportLink,
	useDeleteReportLink,
	useProjectBillings,
	useRemoveBillingBudget,
	useRemoveProjectBilling,
	useReport,
	useReportLinks,
	useSetBillingBudget,
	useSetEntryBillable,
	useSetProjectBilling,
} from "./api";
export {
	type BillingBudget,
	type BillingBudgetInput,
	type BillingBudgetPeriod,
	type BillingBudgetRunning,
	type BillingBudgetScope,
	type BillingBudgetState,
	type BillingBudgetStatus,
	type BillingBudgetUnit,
	type BillingBudgetWords,
	type BillingEntry,
	type BillingLine,
	type BillingMonth,
	type BillingTerm,
	billingBudgetState,
	type ClientBilling,
	type CurrencyTotal,
	describeBillingBudget,
	type EntryBillable,
	entryBillable,
	inForceOn,
	isFutureMonth,
	monthOf,
	monthTitle,
	nextMonth,
	type ProjectBilling,
	type ProjectBillingInput,
	prevMonth,
	type RateSource,
	type Report,
	type ReportEntry,
	type ReportLine,
	type ReportLink,
	type ReportLinkInput,
	type UnattachedHours,
	withPastConsent,
} from "./model";
export {
	BillableSwitch,
	type BillableSwitchProps,
	BillingBudgetDialog,
	type BillingBudgetDialogProps,
	BillingBudgetMeter,
	type BillingBudgetMeterProps,
	BillingBudgetRow,
	type BillingBudgetRowProps,
	describeReportLink,
	ReportLinksBlock,
	type ReportLinksBlockProps,
	reportUrl,
} from "./ui";
