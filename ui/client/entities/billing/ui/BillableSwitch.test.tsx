/**
 * The Billable pill is a switch, so its name says what it switches and its
 * state says which way: the name holds the words drawn on it (WCAG 2.5.3,
 * so "click Billable" works by voice) and stays the same whichever way it
 * is set, which `aria-checked` alone answers.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BillableSwitch } from "./BillableSwitch";

vi.mock("../api", () => ({
	useSetEntryBillable: () => ({ mutate: vi.fn(), isPending: false }),
	useClearEntryBillable: () => ({ mutate: vi.fn(), isPending: false }),
}));

afterEach(cleanup);

describe("BillableSwitch", () => {
	it.each([true, false])("names itself by the words it shows, billable %s", (billable) => {
		render(
			<BillableSwitch
				beatId="b1"
				billable={billable}
				overridden={false}
				entryLabel="Thu Oct 2, 09:00, Website"
			/>,
		);
		const pill = screen.getByRole("switch");
		expect(pill).toHaveAccessibleName("Billable: Thu Oct 2, 09:00, Website");
		expect(pill.textContent?.trim()).toBe("Billable");
		expect(pill).toHaveAttribute("aria-checked", String(billable));
	});
});
