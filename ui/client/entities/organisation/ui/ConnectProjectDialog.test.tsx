/**
 * Connecting a project: "Start fresh" sends no share_from, a chosen day is
 * sent as that day, and the API's refusal is shown in its own words.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/shared/api";
import type { Membership } from "../model";
import { ConnectProjectDialog } from "./ConnectProjectDialog";

const { hooks } = vi.hoisted(() => ({
	hooks: { connect: vi.fn(), toastSuccess: vi.fn() },
}));

vi.mock("../api", () => ({
	useConnectProject: () => ({ mutate: hooks.connect, isPending: false }),
}));
vi.mock("sonner", () => ({ toast: { success: hooks.toastSuccess, error: vi.fn() } }));

function membership(id: string, name: string): Membership {
	return {
		userId: "u-me",
		organisation: {
			id,
			name,
			weekStart: "monday",
			timezone: "Europe/Zurich",
			createdAt: "2026-01-01T00:00:00Z",
		},
		role: "member",
		joinedAt: "2026-03-04T00:00:00Z",
	};
}

const ACME = membership("o1", "Acme");
const PROJECT = { id: "p1", name: "Backend" };
const TODAY = "2026-10-24";

describe("ConnectProjectDialog", () => {
	beforeEach(() => vi.clearAllMocks());
	afterEach(cleanup);

	it("starts fresh by default: the one organisation preselected, share_from null", async () => {
		const onConnected = vi.fn();
		render(
			<ConnectProjectDialog
				project={PROJECT}
				memberships={[ACME]}
				todayIso={TODAY}
				onConnected={onConnected}
				onClose={vi.fn()}
			/>,
		);

		expect(screen.getByRole("radio", { name: /Start fresh/ })).toBeChecked();
		await userEvent.click(screen.getByRole("button", { name: "Connect" }));

		expect(hooks.connect).toHaveBeenCalledTimes(1);
		expect(hooks.connect.mock.calls[0][0]).toEqual({
			organisationId: "o1",
			projectId: "p1",
			shareFrom: null,
		});
		hooks.connect.mock.calls[0][1].onSuccess();
		expect(hooks.toastSuccess).toHaveBeenCalledWith("Connected to Acme");
		expect(onConnected).toHaveBeenCalled();
	});

	it("sends the chosen day when sharing from a date, to the organisation picked", async () => {
		render(
			<ConnectProjectDialog
				project={PROJECT}
				memberships={[ACME, membership("o2", "Globex")]}
				todayIso={TODAY}
				onConnected={vi.fn()}
				onClose={vi.fn()}
			/>,
		);

		// Two organisations: nothing is chosen for the member.
		expect(screen.getByRole("button", { name: "Connect" })).toBeDisabled();
		await userEvent.selectOptions(screen.getByLabelText("Organisation"), "o2");
		await userEvent.click(screen.getByRole("radio", { name: /Share from a date/ }));
		const date = screen.getByLabelText("Share from");
		expect(date).toHaveAttribute("max", TODAY);
		fireEvent.change(date, { target: { value: "2026-03-04" } });
		await userEvent.click(screen.getByRole("button", { name: "Connect" }));

		expect(hooks.connect.mock.calls[0][0]).toEqual({
			organisationId: "o2",
			projectId: "p1",
			shareFrom: "2026-03-04",
		});
	});

	it("shows the API's refusal in its words", async () => {
		const onConnected = vi.fn();
		render(
			<ConnectProjectDialog
				project={PROJECT}
				memberships={[ACME]}
				todayIso={TODAY}
				onConnected={onConnected}
				onClose={vi.fn()}
			/>,
		);

		await userEvent.click(screen.getByRole("button", { name: "Connect" }));
		hooks.connect.mock.calls[0][1].onError(
			new ApiError(409, "A project billed to a client cannot be connected", "PROJECT_HAS_BILLING"),
		);

		expect(await screen.findByRole("alert")).toHaveTextContent(
			"A project billed to a client cannot be connected",
		);
		expect(onConnected).not.toHaveBeenCalled();
	});
});
