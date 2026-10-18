/**
 * The billing budget dialog's promise to the API: every key goes out, the
 * other unit's limit and a monthly budget's first day as null — the API
 * requires each and defaults none — and a 422 lands on the input it names,
 * the dialog staying open. The write is driven through the real mutation
 * and mapper down to `put`, so what is checked is the body sent.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/shared/api";
import { BillingBudgetDialog, type BillingBudgetDialogProps } from "./BillingBudgetDialog";

const { put } = vi.hoisted(() => ({ put: vi.fn() }));

vi.mock("@/shared/api", async () => {
	const actual = await vi.importActual<typeof import("@/shared/api")>("@/shared/api");
	return { ...actual, put };
});
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const STORED = {
	scope: "client",
	scope_id: "c1",
	client_id: "c1",
	currency: "EUR",
	minor_units: 2,
	unit: "hours",
	period: "monthly",
	limit_hours: 40,
	limit_minor: null,
	starts_on: null,
	warn_at_percent: 80,
};

function wrapper({ children }: { children: ReactNode }) {
	const client = new QueryClient({
		defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
	});
	return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function renderDialog(overrides: Partial<BillingBudgetDialogProps> = {}) {
	const props: BillingBudgetDialogProps = {
		scope: "client",
		scopeId: "c1",
		name: "Studio Kite",
		currency: "EUR",
		minorUnits: 2,
		todayIso: "2026-10-18",
		onClose: vi.fn(),
		...overrides,
	};
	render(<BillingBudgetDialog {...props} />, { wrapper });
	return { props, dialog: screen.getByRole("dialog", { name: `${props.name}'s budget` }) };
}

beforeEach(() => {
	put.mockReset();
	put.mockResolvedValue(STORED);
});
afterEach(cleanup);

describe("BillingBudgetDialog", () => {
	it("sends a monthly hours budget with the money limit and the first day as null", async () => {
		const { props, dialog } = renderDialog();
		await userEvent.type(within(dialog).getByLabelText("Budget"), "37,5");
		await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

		await waitFor(() => expect(props.onClose).toHaveBeenCalled());
		expect(put).toHaveBeenCalledWith("/api/billing/budgets/clients/c1", {
			unit: "hours",
			period: "monthly",
			limit_hours: 37.5,
			limit_minor: null,
			starts_on: null,
			warn_at_percent: 80,
		});
	});

	it("sends a total in money from when billing started, with the hours limit as null", async () => {
		put.mockResolvedValue({ ...STORED, scope: "project", scope_id: "p1", unit: "money" });
		const { props, dialog } = renderDialog({
			scope: "project",
			scopeId: "p1",
			name: "Website",
			billingStartedOn: "2026-09-01",
		});
		// Hours typed first, then money: only the unit chosen is sent.
		await userEvent.type(within(dialog).getByLabelText("Budget"), "40");
		await userEvent.click(within(dialog).getByRole("button", { name: "Money (EUR)" }));
		await userEvent.type(within(dialog).getByLabelText("Budget"), "10200");
		expect(
			within(dialog).getByRole("button", { name: "When billing started (Sep 1)" }),
		).toHaveAttribute("aria-pressed", "true");
		await userEvent.clear(within(dialog).getByLabelText("Warn me at"));
		await userEvent.type(within(dialog).getByLabelText("Warn me at"), "90");
		await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

		await waitFor(() => expect(props.onClose).toHaveBeenCalled());
		expect(put).toHaveBeenCalledWith("/api/billing/budgets/projects/p1", {
			unit: "money",
			period: "total",
			limit_hours: null,
			limit_minor: 1_020_000,
			starts_on: "2026-09-01",
			warn_at_percent: 90,
		});
	});

	it("puts the API's refusal of the limit on the limit, and stays open", async () => {
		put.mockRejectedValue(
			new ApiError(422, "Validation failed", "VALIDATION_ERROR", [
				{
					path: "limit_hours",
					message: "Input should be less than or equal to 100000",
					type: "less_than_equal",
				},
			]),
		);
		const { props, dialog } = renderDialog();
		const amount = within(dialog).getByLabelText("Budget");
		await userEvent.type(amount, "40");
		await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

		expect(await within(dialog).findByText(/less than or equal to 100000/)).toBeInTheDocument();
		expect(amount).toHaveAttribute("aria-invalid", "true");
		expect(props.onClose).not.toHaveBeenCalled();
	});
});
