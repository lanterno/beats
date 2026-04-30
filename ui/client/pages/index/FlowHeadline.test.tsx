/**
 * Render-level tests for FlowHeadline. Locks in the home-page card's
 * three contracts: hide when there's nothing to say, render the avg
 * + peak + best repo when there is, and link to the deeper /insights
 * surface for users who want to drill in.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FlowWindowSummary } from "@/shared/api";
import { FlowHeadline } from "./FlowHeadline";

vi.mock("@/entities/session", () => ({
	useFlowWindowsSummary: vi.fn(),
}));

import { useFlowWindowsSummary } from "@/entities/session";

afterEach(cleanup);

function makeSummary(overrides: Partial<FlowWindowSummary> = {}): FlowWindowSummary {
	return {
		count: 23,
		avg: 0.67,
		peak: 0.91,
		peak_at: "2026-05-01T14:32:00Z",
		top_repo: { key: "/Users/me/code/beats", avg: 0.74, count: 18 },
		top_language: { key: "go", avg: 0.7, count: 14 },
		top_bundle: { key: "com.microsoft.VSCode", avg: 0.66, count: 22 },
		...overrides,
	};
}

function renderWithRouter(ui: React.ReactElement) {
	return render(<MemoryRouter>{ui}</MemoryRouter>);
}

beforeEach(() => {
	vi.mocked(useFlowWindowsSummary).mockReturnValue({
		data: makeSummary(),
		isLoading: false,
		// biome-ignore lint/suspicious/noExplicitAny: useQuery's full return shape is irrelevant.
	} as any);
});

describe("FlowHeadline", () => {
	it("renders the avg score in the headline number", () => {
		renderWithRouter(<FlowHeadline />);
		// avg 0.67 → 67 in the headline
		expect(screen.getByText("67")).toBeInTheDocument();
	});

	it("renders peak + count + best repo / language", () => {
		renderWithRouter(<FlowHeadline />);
		expect(screen.getByText("91")).toBeInTheDocument(); // peak
		expect(screen.getByText("23")).toBeInTheDocument(); // count
		expect(screen.getByText("code/beats")).toBeInTheDocument(); // shortened top_repo
		expect(screen.getByText("go")).toBeInTheDocument(); // top_language
	});

	it("links to /insights so the user can drill in", () => {
		renderWithRouter(<FlowHeadline />);
		const link = screen.getByRole("link");
		expect(link).toHaveAttribute("href", "/insights");
	});

	it("hides itself when there are zero windows today", () => {
		// On the home page an "your flow: nothing" card reads as broken;
		// the empty-state guidance lives on /insights.
		vi.mocked(useFlowWindowsSummary).mockReturnValueOnce({
			data: makeSummary({ count: 0, avg: 0, peak: 0, peak_at: null }),
			isLoading: false,
			// biome-ignore lint/suspicious/noExplicitAny: see beforeEach.
		} as any);
		const { container } = renderWithRouter(<FlowHeadline />);
		expect(container.firstChild).toBeNull();
	});

	it("hides itself while loading rather than flashing a placeholder", () => {
		vi.mocked(useFlowWindowsSummary).mockReturnValueOnce({
			data: undefined,
			isLoading: true,
			// biome-ignore lint/suspicious/noExplicitAny: see beforeEach.
		} as any);
		const { container } = renderWithRouter(<FlowHeadline />);
		expect(container.firstChild).toBeNull();
	});

	it("omits the best-repo / best-language line when those axes are null", () => {
		// Editor heartbeats may not have covered the slice — the headline
		// should still render the score block but skip the bottom line.
		vi.mocked(useFlowWindowsSummary).mockReturnValueOnce({
			data: makeSummary({ top_repo: null, top_language: null, top_bundle: null }),
			isLoading: false,
			// biome-ignore lint/suspicious/noExplicitAny: see beforeEach.
		} as any);
		renderWithRouter(<FlowHeadline />);
		expect(screen.getByText("67")).toBeInTheDocument();
		expect(screen.queryByText(/best on/i)).not.toBeInTheDocument();
	});
});
