import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiProject } from "@/shared/api";
import { NewProjectDialog } from "./NewProjectDialog";

const mutateAsync = vi.fn();
const useProjectsMock = vi.fn(() => ({ data: [] }));

vi.mock("../api", () => ({
	useCreateProject: () => ({ mutateAsync, isPending: false }),
	useProjects: () => useProjectsMock(),
}));

vi.mock("@/entities/github", () => ({
	useGitHubStatus: () => ({ data: { connected: false } }),
}));

vi.mock("sonner", () => ({
	toast: { success: vi.fn(), error: vi.fn() },
}));

const CREATED: ApiProject = {
	id: "new-1",
	name: "Alpha",
	description: null,
	color: null,
	archived: false,
	estimation: null,
	weekly_goal: null,
	goal_type: "target",
	goal_overrides: [],
	autostart_repos: [],
};

describe("NewProjectDialog (P1.3 — ProjectForm-hosted)", () => {
	beforeEach(() => {
		mutateAsync.mockReset();
		mutateAsync.mockResolvedValue(CREATED);
		useProjectsMock.mockReturnValue({ data: [] });
	});

	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	it("does not render the dialog content when closed", () => {
		render(<NewProjectDialog open={false} onClose={() => {}} />);
		// Radix Dialog mounts to a portal but renders nothing when closed.
		expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
	});

	it("creates the project with the full canonical field set on submit", async () => {
		const onClose = vi.fn();
		const onCreated = vi.fn();
		render(<NewProjectDialog open onClose={onClose} onCreated={onCreated} />);

		await userEvent.type(screen.getByLabelText("Name"), "  Alpha  ");
		await userEvent.type(screen.getByLabelText(/Weekly goal/), "10");

		await userEvent.click(screen.getByRole("button", { name: "Create project" }));

		// Every backend Project field is sent — defaults supplied for omitted
		// inputs (description=null, category=null, github_repo=null, autostart=[]).
		expect(mutateAsync).toHaveBeenCalledWith(
			expect.objectContaining({
				name: "Alpha",
				weekly_goal: 10,
				description: null,
				category: null,
				github_repo: null,
				autostart_repos: [],
			}),
		);
		expect(onClose).toHaveBeenCalled();
		expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ id: "new-1", name: "Alpha" }));
	});

	it("submits advanced fields when the Advanced disclosure is used", async () => {
		render(<NewProjectDialog open onClose={() => {}} />);

		await userEvent.type(screen.getByLabelText("Name"), "Beta");
		await userEvent.click(screen.getByRole("button", { name: /Advanced/ }));
		await userEvent.type(screen.getByLabelText("Category"), "coding");
		await userEvent.type(screen.getByLabelText("GitHub repo"), "lanterno/beats");

		await userEvent.click(screen.getByRole("button", { name: "Create project" }));

		expect(mutateAsync).toHaveBeenCalledWith(
			expect.objectContaining({
				name: "Beta",
				category: "coding",
				github_repo: "lanterno/beats",
			}),
		);
	});
});
