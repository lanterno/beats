/**
 * Billing Entity - public API
 *
 * A freelance project's billing — its client and dated terms, each saying
 * whether its hours are billable and at what rate — the marks that make one
 * entry billable or not against its term, and what a month comes to per
 * client (docs/billing.md). Each lives in its own collection under
 * /api/billing, never on a project or an entry. The page never prices
 * anything: every amount is the API's.
 */
export {
	useBillableOverrides,
	useBillingMonth,
	useClearEntryBillable,
	useProjectBillings,
	useRemoveProjectBilling,
	useSetEntryBillable,
	useSetProjectBilling,
} from "./api";
export {
	type BillingEntry,
	type BillingLine,
	type BillingMonth,
	type BillingTerm,
	type ClientBilling,
	type CurrencyTotal,
	type EntryBillable,
	entryBillable,
	inForceOn,
	isFutureMonth,
	monthOf,
	nextMonth,
	type ProjectBilling,
	type ProjectBillingInput,
	prevMonth,
	type RateSource,
	type UnattachedHours,
	withPastConsent,
} from "./model";
export { BillableSwitch, type BillableSwitchProps } from "./ui";
