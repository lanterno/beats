import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CoachMemoryDialog } from "./CoachMemoryDialog";

const rewriteMutate = vi.fn();
const deleteMemoryMutate = vi.fn();
const deleteAllMutate = vi.fn();
const useCoachMemoryMock = vi.fn();

vi.mock("@/entities/coach", () => ({
	useCoachMemory: () => useCoachMemoryMock(),
	useRewriteMemory: () => ({ mutate: rewriteMutate, isPending: false }),
	useDeleteMemory: () => ({ mutate: deleteMemoryMutate, isPending: false }),
	useDeleteCoachData: () => ({ mutate: deleteAllMutate, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("CoachMemoryDialog", () => {
	beforeEach(() => {
		rewriteMutate.mockReset();
		deleteMemoryMutate.mockReset();
		deleteAllMutate.mockReset();
		useCoachMemoryMock.mockReset();
		useCoachMemoryMock.mockReturnValue({
			data: { content: "You focus best in the morning.", updated_at: "2026-05-20T10:00:00Z" },
			isLoading: false,
		});
	});

	afterEach(cleanup);

	it("renders nothing when closed", () => {
		const { container } = render(<CoachMemoryDialog open={false} onClose={() => {}} />);
		expect(container).toBeEmptyDOMElement();
	});

	it("shows the stored memory content", () => {
		render(<CoachMemoryDialog open onClose={() => {}} />);
		expect(screen.getByText("You focus best in the morning.")).toBeInTheDocument();
	});

	it("rewrites memory from recent activity", async () => {
		render(<CoachMemoryDialog open onClose={() => {}} />);
		await userEvent.click(screen.getByRole("button", { name: /Rewrite from recent activity/ }));
		expect(rewriteMutate).toHaveBeenCalledTimes(1);
	});

	it("requires confirmation before deleting memory", async () => {
		render(<CoachMemoryDialog open onClose={() => {}} />);
		await userEvent.click(screen.getByRole("button", { name: /Delete memory/ }));
		// Not deleted yet — a confirm step appears first.
		expect(deleteMemoryMutate).not.toHaveBeenCalled();
		await userEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
		expect(deleteMemoryMutate).toHaveBeenCalledTimes(1);
	});

	it("requires confirmation before wiping all coach data", async () => {
		render(<CoachMemoryDialog open onClose={() => {}} />);
		await userEvent.click(screen.getByRole("button", { name: /Delete all coach data/ }));
		expect(deleteAllMutate).not.toHaveBeenCalled();
		await userEvent.click(screen.getByRole("button", { name: "Delete everything" }));
		expect(deleteAllMutate).toHaveBeenCalledTimes(1);
	});

	it("disables Delete memory when there is no memory yet", () => {
		useCoachMemoryMock.mockReturnValue({ data: { content: null }, isLoading: false });
		render(<CoachMemoryDialog open onClose={() => {}} />);
		expect(screen.getByRole("button", { name: /Delete memory/ })).toBeDisabled();
	});
});
