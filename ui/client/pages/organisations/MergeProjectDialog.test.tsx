/**
 * The merge dialog (#346). The rules live in the API and are tested there;
 * what is pinned here is the dialog's half of the contract: the merge names
 * the chosen target, and a refusal — a frozen month — is shown in the API's
 * words where the choice was made, not swallowed into a toast.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { OrgProject } from "@/entities/organisation";
import { MergeProjectDialog } from "./MergeProjectDialog";

const { merge } = vi.hoisted(() => ({ merge: vi.fn() }));

vi.mock("@/entities/organisation", async () => {
	const actual =
		await vi.importActual<typeof import("@/entities/organisation")>("@/entities/organisation");
	return {
		...actual,
		useMergeOrgProject: () => ({ isPending: false, mutate: merge }),
	};
});

function project(id: string, name: string): OrgProject {
	return { id, name, archived: false, kind: "day_job", members: [] };
}

afterEach(() => {
	cleanup();
	merge.mockReset();
});

describe("MergeProjectDialog", () => {
	it("merges into the chosen project", () => {
		render(
			<MergeProjectDialog
				organisationId="o1"
				project={project("dup", "Day job")}
				targets={[project("plat", "Platform"), project("ops", "Ops")]}
				onClose={vi.fn()}
			/>,
		);

		fireEvent.change(screen.getByLabelText("The project that stays"), {
			target: { value: "ops" },
		});
		fireEvent.click(screen.getByRole("button", { name: "Merge" }));

		expect(merge).toHaveBeenCalledWith({ projectId: "dup", into: "ops" }, expect.anything());
	});

	it("shows a refusal in the API's words, where the choice was made", async () => {
		merge.mockImplementation((_args, { onError }) =>
			onError({
				status: 409,
				detail: "This month's timesheet is approved; ask for it to be reopened",
				code: "PERIOD_APPROVED",
			}),
		);
		render(
			<MergeProjectDialog
				organisationId="o1"
				project={project("dup", "Day job")}
				targets={[project("plat", "Platform")]}
				onClose={vi.fn()}
			/>,
		);

		fireEvent.click(screen.getByRole("button", { name: "Merge" }));

		expect(await screen.findByRole("alert")).toBeTruthy();
	});
});
