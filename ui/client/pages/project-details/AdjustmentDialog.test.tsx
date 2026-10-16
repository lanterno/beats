/**
 * The adjustment dialog: Pay out goes out as a negative delta; the day runs
 * from the contract's first through today; a day that already holds one
 * says it will be replaced; a moved day is posted before the old one is
 * deleted; and the API's refusal is shown in the dialog, which stays open.
 */
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LedgerAdjustment } from "@/entities/project";
import { ApiError } from "@/shared/api";
import { AdjustmentDialog, type AdjustmentDialogProps } from "./AdjustmentDialog";

const { hooks } = vi.hoisted(() => ({
	hooks: { record: vi.fn(), remove: vi.fn(), calls: [] as string[] },
}));

vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return {
		...actual,
		useRecordAdjustment: () => ({ mutateAsync: hooks.record }),
		useRemoveAdjustment: () => ({ mutateAsync: hooks.remove }),
	};
});
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const TODAY = "2026-09-10";
const PAYOUT: LedgerAdjustment = {
	id: "a1",
	date: "2026-09-01",
	kind: "delta",
	hours: -40,
	note: "August",
	applied: -40,
};

function renderDialog(overrides: Partial<AdjustmentDialogProps> = {}) {
	const props: AdjustmentDialogProps = {
		projectId: "p1",
		since: "2026-01-05",
		todayIso: TODAY,
		adjustments: [],
		onClose: vi.fn(),
		...overrides,
	};
	render(<AdjustmentDialog {...props} />);
	return { props, dialog: screen.getByRole("dialog") };
}

beforeEach(() => {
	hooks.calls = [];
	hooks.record.mockReset().mockImplementation(async () => {
		hooks.calls.push("record");
	});
	hooks.remove.mockReset().mockImplementation(async () => {
		hooks.calls.push("remove");
	});
});
afterEach(cleanup);

describe("AdjustmentDialog", () => {
	it("sends a payout as a negative delta on the day picked", async () => {
		const { props, dialog } = renderDialog();
		await userEvent.type(within(dialog).getByLabelText("Hours"), "12.5");
		await userEvent.type(within(dialog).getByLabelText("Note"), "Paid with August");
		await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

		expect(hooks.record).toHaveBeenCalledWith({
			projectId: "p1",
			input: { date: TODAY, kind: "delta", hours: -12.5, note: "Paid with August" },
		});
		await waitFor(() => expect(props.onClose).toHaveBeenCalled());
	});

	it("dates an adjustment from the contract's first day through today", async () => {
		const { dialog } = renderDialog();
		const day = within(dialog).getByLabelText("Day");
		expect(day).toHaveAttribute("min", "2026-01-05");
		expect(day).toHaveAttribute("max", TODAY);

		await userEvent.type(within(dialog).getByLabelText("Hours"), "8");
		await userEvent.clear(day);
		await userEvent.type(day, "2026-09-11");
		await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
		expect(dialog).toHaveTextContent("An adjustment can be dated today at the latest.");
		expect(hooks.record).not.toHaveBeenCalled();
	});

	it("says a save replaces what a day already holds", async () => {
		const { dialog } = renderDialog({ adjustments: [PAYOUT] });
		expect(dialog).not.toHaveTextContent("Replaces");
		const day = within(dialog).getByLabelText("Day");
		await userEvent.clear(day);
		await userEvent.type(day, PAYOUT.date);
		expect(dialog).toHaveTextContent("Replaces the payout on this day.");
	});

	it("posts a moved adjustment on its new day before deleting the old", async () => {
		const { dialog } = renderDialog({ adjustments: [PAYOUT], editing: PAYOUT });
		expect(within(dialog).getByLabelText("Hours")).toHaveValue(40);
		expect(within(dialog).getByRole("button", { name: "Pay out" })).toHaveAttribute(
			"aria-pressed",
			"true",
		);
		const day = within(dialog).getByLabelText("Day");
		await userEvent.clear(day);
		await userEvent.type(day, "2026-09-02");
		await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

		await waitFor(() => expect(hooks.calls).toEqual(["record", "remove"]));
		expect(hooks.record).toHaveBeenCalledWith({
			projectId: "p1",
			input: { date: "2026-09-02", kind: "delta", hours: -40, note: "August" },
		});
		expect(hooks.remove).toHaveBeenCalledWith({ projectId: "p1", adjustmentId: "a1" });
	});

	it("saves on the same day with one post, and keeps the old one when the post fails", async () => {
		hooks.record.mockRejectedValueOnce(
			new ApiError(
				409,
				"A balance adjustment must be dated from the contract's first day through today",
				"ADJUSTMENT_OUTSIDE_BALANCE",
			),
		);
		const { props, dialog } = renderDialog({ adjustments: [PAYOUT], editing: PAYOUT });
		await userEvent.click(within(dialog).getByRole("button", { name: "Reset to" }));
		await userEvent.clear(within(dialog).getByLabelText("Hours"));
		await userEvent.type(within(dialog).getByLabelText("Hours"), "0");
		await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

		expect(await within(dialog).findByRole("alert")).toHaveTextContent(
			"A balance adjustment must be dated from the contract's first day through today",
		);
		expect(hooks.record).toHaveBeenCalledWith({
			projectId: "p1",
			input: { date: PAYOUT.date, kind: "reset", hours: 0, note: "August" },
		});
		expect(hooks.remove).not.toHaveBeenCalled();
		expect(props.onClose).not.toHaveBeenCalled();
	});
});
