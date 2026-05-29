import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiProject } from "@/shared/api";
import { NewProjectDialog } from "./NewProjectDialog";

const mutateAsync = vi.fn();

vi.mock("../api", () => ({
	useCreateProject: () => ({ mutateAsync, isPending: false }),
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
};

describe("NewProjectDialog", () => {
	beforeEach(() => {
		mutateAsync.mockReset();
		mutateAsync.mockResolvedValue(CREATED);
	});

	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	it("renders nothing when closed", () => {
		const { container } = render(<NewProjectDialog open={false} onClose={() => {}} />);
		expect(container).toBeEmptyDOMElement();
	});

	it("disables Create until a name is entered", async () => {
		render(<NewProjectDialog open onClose={() => {}} />);
		const create = screen.getByRole("button", { name: "Create project" });
		expect(create).toBeDisabled();

		await userEvent.type(screen.getByLabelText("Name"), "Alpha");
		expect(create).toBeEnabled();
	});

	it("creates the project and reports the created project, then closes", async () => {
		const onClose = vi.fn();
		const onCreated = vi.fn();
		render(<NewProjectDialog open onClose={onClose} onCreated={onCreated} />);

		await userEvent.type(screen.getByLabelText("Name"), "  Alpha  ");
		await userEvent.click(screen.getByRole("button", { name: "Create project" }));

		// Name is trimmed; an empty goal is sent as null (no convenience default).
		expect(mutateAsync).toHaveBeenCalledWith({ name: "Alpha", weekly_goal: null });
		expect(onClose).toHaveBeenCalled();
		expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ id: "new-1", name: "Alpha" }));
	});

	it("passes a numeric weekly goal through", async () => {
		render(<NewProjectDialog open onClose={() => {}} />);
		await userEvent.type(screen.getByLabelText("Name"), "Beta");
		await userEvent.type(screen.getByLabelText(/Weekly goal/), "10");
		await userEvent.click(screen.getByRole("button", { name: "Create project" }));

		expect(mutateAsync).toHaveBeenCalledWith({ name: "Beta", weekly_goal: 10 });
	});
});
