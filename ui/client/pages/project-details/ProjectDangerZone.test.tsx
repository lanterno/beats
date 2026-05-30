import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectDangerZone } from "./ProjectDangerZone";

const archiveMutate = vi.fn();
const unarchiveMutate = vi.fn();
const navigateMock = vi.fn();

vi.mock("@/entities/project", () => ({
	useArchiveProject: () => ({ mutate: archiveMutate, isPending: false }),
	useUnarchiveProject: () => ({ mutate: unarchiveMutate, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("react-router-dom", async () => {
	const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
	return { ...actual, useNavigate: () => navigateMock };
});

function renderZone(props: Partial<React.ComponentProps<typeof ProjectDangerZone>> = {}) {
	return render(
		<MemoryRouter>
			<ProjectDangerZone projectId="p1" projectName="Alpha" archived={false} {...props} />
		</MemoryRouter>,
	);
}

describe("ProjectDangerZone", () => {
	beforeEach(() => {
		archiveMutate.mockReset();
		unarchiveMutate.mockReset();
		navigateMock.mockReset();
	});

	afterEach(cleanup);

	it("requires confirmation before archiving and then archives + navigates to /app", async () => {
		renderZone();

		// Clicking the primary archive button reveals a confirm step — it does NOT
		// archive immediately. Same correctness bar as the session-delete inline
		// confirm we shipped earlier.
		await userEvent.click(screen.getByRole("button", { name: "Archive project" }));
		expect(archiveMutate).not.toHaveBeenCalled();

		await userEvent.click(screen.getByRole("button", { name: "Archive project" }));
		expect(archiveMutate).toHaveBeenCalledWith("p1", expect.anything());

		// Simulate the mutation's onSuccess (passed via the second arg) to confirm
		// the post-archive navigation runs — the user shouldn't land on a stale
		// page for a project that has just left every active picker.
		const handlers = archiveMutate.mock.calls[0][1];
		handlers.onSuccess?.();
		expect(navigateMock).toHaveBeenCalledWith("/app");
	});

	it("allows cancelling the archive confirm step", async () => {
		renderZone();

		await userEvent.click(screen.getByRole("button", { name: "Archive project" }));
		await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
		expect(screen.getByRole("button", { name: "Archive project" })).toBeInTheDocument();
		expect(archiveMutate).not.toHaveBeenCalled();
	});

	it("renders the restore control when the project is archived", async () => {
		renderZone({ archived: true });

		expect(screen.queryByRole("button", { name: /Archive project/ })).not.toBeInTheDocument();
		await userEvent.click(screen.getByRole("button", { name: "Restore project" }));
		expect(unarchiveMutate).toHaveBeenCalledWith("p1", expect.anything());
	});
});
