/**
 * The billing dialog's two promises: "Billable from" starts on the project's
 * first tracked day, or today when nothing is tracked, so the history it
 * bills is in view before the save; and the API's refusal of a rate lands
 * on the rate input, the dialog staying open.
 */
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Client } from "@/entities/client";
import { ApiError } from "@/shared/api";
import { BillingDialog, type BillingDialogProps } from "./BillingDialog";

const { hooks } = vi.hoisted(() => ({
	hooks: { setBilling: vi.fn() },
}));

const KITE: Client = {
	id: "c1",
	name: "Studio Kite",
	currency: "EUR",
	minorUnits: 2,
	rates: [{ effectiveFrom: "2026-01-01", rateMinor: 8500 }],
	archived: false,
	createdAt: "2026-01-01T00:00:00Z",
	currencyLocked: true,
};

vi.mock("@/entities/client", async () => {
	const actual = await vi.importActual<typeof import("@/entities/client")>("@/entities/client");
	return {
		...actual,
		useClients: ({ archived = false }: { archived?: boolean } = {}) => ({
			data: archived ? [] : [KITE],
		}),
		useCreateClient: () => ({ mutateAsync: vi.fn() }),
	};
});
vi.mock("@/entities/billing", async () => {
	const actual = await vi.importActual<typeof import("@/entities/billing")>("@/entities/billing");
	return {
		...actual,
		useSetProjectBilling: () => ({ mutateAsync: hooks.setBilling, isPending: false }),
	};
});
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const TODAY = "2026-10-17";

function renderDialog(overrides: Partial<BillingDialogProps> = {}) {
	const props: BillingDialogProps = {
		project: { id: "p1", name: "Website" },
		mode: { kind: "attach" },
		todayIso: TODAY,
		onClose: vi.fn(),
		...overrides,
	};
	render(<BillingDialog {...props} />);
	return { props, dialog: screen.getByRole("dialog", { name: "Bill this project" }) };
}

beforeEach(() => {
	hooks.setBilling.mockReset();
});
afterEach(cleanup);

describe("BillingDialog", () => {
	it("bills from the first tracked day, as all of the project's time so far", async () => {
		hooks.setBilling.mockResolvedValue({});
		const { props, dialog } = renderDialog({ firstTrackedIso: "2026-03-04" });
		expect(within(dialog).getByLabelText("Billable from")).toHaveValue("2026-03-04");
		expect(dialog).toHaveTextContent("All of its time so far");

		await userEvent.selectOptions(within(dialog).getByLabelText("Client"), "c1");
		await userEvent.click(within(dialog).getByRole("button", { name: "Bill it" }));
		expect(hooks.setBilling).toHaveBeenCalledWith({
			projectId: "p1",
			input: {
				clientId: "c1",
				terms: [{ effectiveFrom: "2026-03-04", billable: true, rateMinor: undefined }],
			},
			rewritePast: false,
		});
		await waitFor(() => expect(props.onClose).toHaveBeenCalled());
	});

	it("bills from today when nothing is tracked yet", () => {
		const { dialog } = renderDialog();
		expect(within(dialog).getByLabelText("Billable from")).toHaveValue(TODAY);
		expect(dialog).toHaveTextContent("From today");
		expect(dialog).not.toHaveTextContent("All of its time so far");
	});

	it("puts the API's refusal of the rate on the rate input and stays open", async () => {
		hooks.setBilling.mockRejectedValue(
			new ApiError(422, "Validation failed", "VALIDATION_ERROR", [
				{
					path: "terms.0.rate_minor",
					message: "Input should be less than or equal to 100000000",
					type: "less_than_equal",
				},
			]),
		);
		const { props, dialog } = renderDialog();
		await userEvent.selectOptions(within(dialog).getByLabelText("Client"), "c1");
		await userEvent.type(within(dialog).getByLabelText("Its own rate, per hour"), "95");
		await userEvent.click(within(dialog).getByRole("button", { name: "Bill it" }));

		const rate = within(dialog).getByLabelText("Its own rate, per hour");
		await waitFor(() => expect(rate).toHaveAttribute("aria-invalid", "true"));
		expect(rate).toHaveAccessibleDescription("Input should be less than or equal to 100000000");
		expect(hooks.setBilling.mock.calls[0][0].input.terms[0].rateMinor).toBe(9500);
		expect(props.onClose).not.toHaveBeenCalled();
	});
});
