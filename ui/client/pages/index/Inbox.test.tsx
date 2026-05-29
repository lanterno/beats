import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Inbox } from "./Inbox";

const mutate = vi.fn();
const useInboxMock = vi.fn();

vi.mock("@/entities/intelligence", () => ({
	useInbox: () => useInboxMock(),
	useDismissInboxItem: () => ({ mutate }),
}));

function renderInbox() {
	return render(
		<MemoryRouter>
			<Inbox />
		</MemoryRouter>,
	);
}

describe("Inbox", () => {
	beforeEach(() => {
		mutate.mockReset();
		useInboxMock.mockReset();
	});

	it("dismisses any inbox kind by its full server id", async () => {
		useInboxMock.mockReturnValue({
			data: {
				items: [
					{
						id: "suggestion:p1:2026-05-29",
						kind: "suggestion",
						severity: "low",
						title: "Plan 30 min on Alpha",
						body: "unmet goal",
					},
					{
						id: "project_health:p2",
						kind: "project_health",
						severity: "medium",
						title: "Beta needs attention",
						body: "stale",
					},
				],
			},
			isLoading: false,
		});

		renderInbox();
		expect(screen.getByText("Plan 30 min on Alpha")).toBeInTheDocument();

		// Dismissing a SUGGESTION must hit the server with its full prefixed id
		// (the old code only dismissed patterns server-side, leaking suggestions
		// to per-day localStorage).
		await userEvent.click(screen.getByRole("button", { name: "Dismiss Plan 30 min on Alpha" }));
		expect(mutate).toHaveBeenCalledWith("suggestion:p1:2026-05-29");

		// And a project_health item dismisses by its id too.
		await userEvent.click(screen.getByRole("button", { name: "Dismiss Beta needs attention" }));
		expect(mutate).toHaveBeenCalledWith("project_health:p2");
	});

	it("renders nothing while loading", () => {
		useInboxMock.mockReturnValue({ data: undefined, isLoading: true });
		const { container } = renderInbox();
		expect(container).toBeEmptyDOMElement();
	});

	it("renders nothing when there are no items", () => {
		useInboxMock.mockReturnValue({ data: { items: [] }, isLoading: false });
		const { container } = renderInbox();
		expect(container).toBeEmptyDOMElement();
	});
});
