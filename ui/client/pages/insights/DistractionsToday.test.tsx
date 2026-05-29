import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DistractionsToday } from "./DistractionsToday";

const useRecentDriftMock = vi.fn();

vi.mock("@/entities/session", () => ({
	useRecentDrift: () => useRecentDriftMock(),
}));

describe("DistractionsToday", () => {
	beforeEach(() => useRecentDriftMock.mockReset());
	afterEach(cleanup);

	it("renders nothing when there is no drift today", () => {
		useRecentDriftMock.mockReturnValue({ data: [], isLoading: false });
		const { container } = render(<DistractionsToday />);
		expect(container).toBeEmptyDOMElement();
	});

	it("renders nothing while loading", () => {
		useRecentDriftMock.mockReturnValue({ data: undefined, isLoading: true });
		const { container } = render(<DistractionsToday />);
		expect(container).toBeEmptyDOMElement();
	});

	it("summarizes total time and top distracting apps", () => {
		useRecentDriftMock.mockReturnValue({
			data: [
				{ id: "d1", started_at: "x", duration_seconds: 300, bundle_id: "com.google.Chrome" },
				{ id: "d2", started_at: "x", duration_seconds: 120, bundle_id: "com.google.Chrome" },
				{
					id: "d3",
					started_at: "x",
					duration_seconds: 180,
					bundle_id: "com.tinyspeck.slackmacgap",
				},
			],
			isLoading: false,
		});
		render(<DistractionsToday />);

		expect(screen.getByText("Distractions today")).toBeInTheDocument();
		// Bundle ids resolve to friendly labels.
		expect(screen.getByText("Chrome")).toBeInTheDocument();
		expect(screen.getByText("Slack")).toBeInTheDocument();
		// 3 drift events total.
		expect(screen.getByText("3")).toBeInTheDocument();
	});
});
