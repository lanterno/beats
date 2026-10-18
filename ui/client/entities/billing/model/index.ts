// A billing budget in words, and its state against the clock

// The Clients page's month navigator
export { isFutureMonth, monthOf, nextMonth, prevMonth } from "./billingMonth";
export { type BillingBudgetWords, billingBudgetState, describeBillingBudget } from "./budget";
// Mappers
export {
	toApiBillingBudgetInput,
	toApiProjectBillingInput,
	toBillingBudget,
	toBillingBudgetStatus,
	toBillingMonth,
	toOverrideMap,
	toProjectBilling,
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
	UnattachedHours,
} from "./types";
// Ask before a write that changes a month already over
export { withPastConsent } from "./withPastConsent";
