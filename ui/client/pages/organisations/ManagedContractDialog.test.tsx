/**
 * The employer's managed-contract dialog (#349). What is worth pinning here
 * is the rule the API does not enforce: terms are editable only where the
 * organisation manages the contract, because on an unmanaged assignment they
 * are the member's own and writing them from here would be the silent
 * recomputation decision 21 forbids. The rest — that a term write carries
 * the whole contract and keeps management on — is the shape a 409 or a lost
 * holiday list would come from.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ApiContract } from "@/shared/api";
import { ManagedContractDialog } from "./ManagedContractDialog";

const { state, setContract } = vi.hoisted(() => ({
	state: {
		data: undefined as unknown,
		error: null as unknown,
	},
	setContract: vi.fn(),
}));

vi.mock("@/entities/organisation", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/organisation")>("@/entities/organisation");
	return {
		...actual,
		useManagedContract: () => ({ data: state.data, error: state.error }),
		useSetManagedContract: () => ({ isPending: false, mutate: setContract }),
	};
});

/** A contract as the wire carries it: two terms, a region, a company day. */
function wireContract(): ApiContract {
	return {
		terms: [
			{
				effective_from: "2026-01-01",
				schedule_type: "full_time",
				full_time_hours: 40,
				percentage: 1,
				weekly_hours: null,
				note: null,
			},
			{
				effective_from: "2026-06-01",
				schedule_type: "part_time",
				full_time_hours: 40,
				percentage: 0.8,
				weekly_hours: null,
				note: null,
			},
		],
		holiday_country: "DE",
		holiday_subdivision: "BY",
		opening_balance_hours: 12,
		ended_on: null,
		company_holidays: [{ date: "2026-12-24", name: "Christmas Eve" }],
		holidays_not_given: ["2026-05-01"],
		vacation: null,
	};
}

function renderDialog() {
	render(
		<ManagedContractDialog
			organisationId="o1"
			projectId="p1"
			projectName="Platform"
			userId="u1"
			memberName="Mina"
			onClose={vi.fn()}
		/>,
	);
}

afterEach(() => {
	cleanup();
	setContract.mockReset();
	state.data = undefined;
	state.error = null;
});

describe("ManagedContractDialog", () => {
	it("offers no term editing while the contract is the member's own", () => {
		state.data = { projectId: "p1", userId: "u1", managed: false, contract: wireContract() };
		renderDialog();

		expect(screen.getByText(/A contract with 2 dated terms is on record\./)).toBeTruthy();
		expect(screen.queryByText("Change contract from…")).toBeNull();
		expect(screen.getByText(/Terms are the member's own while it is unmanaged/)).toBeTruthy();
	});

	it("lists the terms with the one in force once the organisation manages it", () => {
		state.data = { projectId: "p1", userId: "u1", managed: true, contract: wireContract() };
		// Between the two terms, so "in force" is January's and not simply the
		// last row — which is what it would be on any date after June.
		vi.useFakeTimers();
		vi.setSystemTime(new Date("2026-03-15T10:00:00Z"));
		try {
			renderDialog();

			expect(screen.getByText("Change contract from…")).toBeTruthy();
			const inForce = screen.getByText("(in force)").closest("li");
			expect(inForce?.textContent).toContain("Jan 1, 2026");
		} finally {
			vi.useRealTimers();
		}
	});

	it("keeps the rest of the contract when a term is removed", async () => {
		state.data = { projectId: "p1", userId: "u1", managed: true, contract: wireContract() };
		renderDialog();

		fireEvent.click(screen.getByLabelText("Remove the term from Jun 1, 2026"));

		await waitFor(() => expect(setContract).toHaveBeenCalled());
		const [args] = setContract.mock.calls[0];
		expect(args.managed).toBe(true);
		// June's term goes; January's stays.
		expect(args.contract.terms).toHaveLength(1);
		expect(args.contract.terms[0].effective_from).toBe("2026-01-01");
		// The holiday lists and the opening balance ride along: the member's
		// form owns them, and a write that dropped them would clear them.
		expect(args.contract.company_holidays).toEqual([{ date: "2026-12-24", name: "Christmas Eve" }]);
		expect(args.contract.holidays_not_given).toEqual(["2026-05-01"]);
		expect(args.contract.opening_balance_hours).toBe(12);
		expect(args.contract.holiday_country).toBe("DE");
	});

	it("refuses to remove the last term, since a contract needs one", () => {
		const one = wireContract();
		one.terms = [one.terms[0]];
		state.data = { projectId: "p1", userId: "u1", managed: true, contract: one };
		renderDialog();

		const remove = screen.getByLabelText(/Remove the term from/, { selector: "button" });
		expect(remove.hasAttribute("disabled")).toBe(true);
	});

	it("stops offering term edits once the toggle says the pen goes back", () => {
		state.data = { projectId: "p1", userId: "u1", managed: true, contract: wireContract() };
		renderDialog();
		expect(screen.getByText("Change contract from…")).toBeTruthy();

		fireEvent.click(screen.getByLabelText("Managed by the organisation"));

		expect(screen.queryByText("Change contract from…")).toBeNull();
	});

	it("says what to do first when there is no contract to manage", () => {
		state.data = { projectId: "p1", userId: "u1", managed: false, contract: null };
		renderDialog();

		expect(screen.getByText("No contract is on record.")).toBeTruthy();
		expect(screen.queryByText("Change contract from…")).toBeNull();
	});
});
