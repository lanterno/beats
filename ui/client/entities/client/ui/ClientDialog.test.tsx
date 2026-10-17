/**
 * A client in a currency withdrawn since it was chosen: the API keeps
 * reading it (`_WITHDRAWN` in domain/currencies.py) but no longer lists it
 * among the codes a client may pick, and the dialog must still show it as
 * the client's, and send it back unchanged.
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Client } from "../model";
import { ClientDialog } from "./ClientDialog";

vi.mock("../api", () => ({
	useCurrencies: () => ({ data: [{ code: "EUR", minorUnits: 2 }] }),
}));

const LEV: Client = {
	id: "c1",
	name: "Sofia Studio",
	currency: "BGN",
	minorUnits: 2,
	rates: [],
	archived: false,
	createdAt: "2025-06-01T00:00:00Z",
	currencyLocked: false,
};

afterEach(cleanup);

describe("ClientDialog", () => {
	it("keeps a withdrawn currency as the client's own", async () => {
		const onSave = vi.fn().mockResolvedValue(true);
		render(<ClientDialog client={LEV} todayIso="2026-10-17" onSave={onSave} onClose={vi.fn()} />);

		const picker = screen.getByLabelText("Currency");
		expect(picker).toHaveValue("BGN");
		await userEvent.selectOptions(picker, "EUR");
		await userEvent.selectOptions(picker, "BGN");

		await userEvent.click(screen.getByRole("button", { name: "Save" }));
		expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ currency: "BGN" }));
	});
});
