/**
 * Client Entity - public API
 *
 * Who you bill: a record in your own account, with a contact, one ISO 4217
 * currency and a dated default rate (docs/billing.md). Archive is the
 * normal way out; delete is refused while a project is billed to it.
 */
export {
	clientKeys,
	useArchiveClient,
	useClients,
	useCreateClient,
	useCurrencies,
	useDeleteClient,
	useUnarchiveClient,
	useUpdateClient,
} from "./api";
export type { Client, ClientInput, Currency, RateTerm } from "./model";
export { ClientDialog, type ClientDialogProps } from "./ui";
