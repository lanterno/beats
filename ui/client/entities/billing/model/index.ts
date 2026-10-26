// A billing budget in words, and its state against the clock

// The Clients page's month navigator
export { isFutureMonth, monthOf, monthTitle, nextMonth, prevMonth } from "./billingMonth";
export { type BillingBudgetWords, billingBudgetState, describeBillingBudget } from "./budget";
// Mappers
export {
	toApiBillingBudgetInput,
	toApiProjectBillingInput,
	toApiReportLinkInput,
	toBillingBudget,
	toBillingBudgetStatus,
	toBillingMonth,
	toOverrideMap,
	toProjectBilling,
	toReport,
	toReportLink,
} from "./mappers";
// Whether an entry is billable: the API's flag rule, mirrored
export { type EntryBillable, entryBillable, inForceOn } from "./resolve";
export type {
	BillingBudget,
	BillingBudgetInput,
	BillingBudgetPeriod,
	BillingBudgetRunning,
	BillingBudgetScope,
	BillingBudgetState,
	BillingBudgetStatus,
	BillingBudgetUnit,
	BillingEntry,
	BillingLine,
	BillingMonth,
	BillingTerm,
	ClientBilling,
	CurrencyTotal,
	ProjectBilling,
	ProjectBillingInput,
	RateSource,
	Report,
	ReportEntry,
	ReportLine,
	ReportLink,
	ReportLinkInput,
	UnattachedHours,
} from "./types";
// Ask before a write that changes a month already over
export { withPastConsent } from "./withPastConsent";
