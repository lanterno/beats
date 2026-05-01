/**
 * Render-level tests for FlowHeadline. Locks in the home-page card's
 * contracts:
 *
 * - render today's slice when populated (avg + peak + count + best
 *   repo / language) and link to /insights
 * - fall back to yesterday's slice when today is empty (early-morning
 *   case) with a clear "Flow yesterday" label
 * - hide entirely when both today AND yesterday are empty
 * - hide while loading (no flash of placeholder)
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
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

const EMPTY: FlowWindowSummary = {
	count: 0,
	avg: 0,
	peak: 0,
	peak_at: null,
	top_repo: null,
	top_language: null,
	top_bundle: null,
};

function renderWithRouter(ui: React.ReactElement) {
	return render(<MemoryRouter>{ui}</MemoryRouter>);
}

/** Wires the hook so the first call (today) and second call (yesterday)
 * return distinct values. The component always calls today first, so
 * order is stable. */
function setSummaries(opts: {
	today: FlowWindowSummary | undefined;
	yesterday: FlowWindowSummary | undefined;
	loading?: boolean;
}) {
	const mock = vi.mocked(useFlowWindowsSummary);
	mock.mockReset();
	let call = 0;
	mock.mockImplementation(() => {
		const data = call === 0 ? opts.today : opts.yesterday;
		call++;
		// biome-ignore lint/suspicious/noExplicitAny: useQuery's full return shape is irrelevant.
		return { data, isLoading: opts.loading ?? false } as any;
	});
}

beforeEach(() => {
	// Default: today populated, yesterday irrelevant. Each test
	// override re-stubs as needed.
	setSummaries({ today: makeSummary(), yesterday: EMPTY });
});

describe("FlowHeadline", () => {
	it("renders today's avg score in the headline number when populated", () => {
		renderWithRouter(<FlowHeadline />);
		expect(screen.getByText("Flow today")).toBeInTheDocument();
		expect(screen.getByText("67")).toBeInTheDocument();
	});

	it("renders peak + count + best repo / language", () => {
		renderWithRouter(<FlowHeadline />);
		expect(screen.getByText("91")).toBeInTheDocument();
		expect(screen.getByText("23")).toBeInTheDocument();
		expect(screen.getByText("code/beats")).toBeInTheDocument();
		expect(screen.getByText("go")).toBeInTheDocument();
	});

	it("links to /insights so the user can drill in", () => {
		renderWithRouter(<FlowHeadline />);
		expect(screen.getByRole("link")).toHaveAttribute("href", "/insights");
	});

	it("falls back to yesterday's slice and labels it 'Flow yesterday' when today is empty", () => {
		// Early-morning case: user opened the laptop, no windows yet
		// today, but yesterday's pattern is still useful context.
		setSummaries({
			today: EMPTY,
			yesterday: makeSummary({ avg: 0.5, count: 80 }),
		});
		renderWithRouter(<FlowHeadline />);
		expect(screen.getByText("Flow yesterday")).toBeInTheDocument();
		expect(screen.getByText("50")).toBeInTheDocument(); // avg 0.5 → 50
		expect(screen.queryByText("Flow today")).not.toBeInTheDocument();
	});

	it("hides entirely when both today AND yesterday are empty", () => {
		setSummaries({ today: EMPTY, yesterday: EMPTY });
		const { container } = renderWithRouter(<FlowHeadline />);
		expect(container.firstChild).toBeNull();
	});

	it("hides while loading rather than flashing a placeholder", () => {
		setSummaries({ today: undefined, yesterday: undefined, loading: true });
		const { container } = renderWithRouter(<FlowHeadline />);
		expect(container.firstChild).toBeNull();
	});

	it("omits the best-repo / best-language line when those axes are null", () => {
		setSummaries({
			today: makeSummary({ top_repo: null, top_language: null, top_bundle: null }),
			yesterday: EMPTY,
		});
		renderWithRouter(<FlowHeadline />);
		expect(screen.getByText("67")).toBeInTheDocument();
		expect(screen.queryByText(/best on/i)).not.toBeInTheDocument();
	});

	it("clicks 'best on <repo>' to deep-link Insights pre-filtered by repo", () => {
		// Tests the URL navigation, not the rendered Insights page.
		// LocationProbe captures the URL after the click.
		let lastSearch = "";
		const LocationProbe = () => {
			lastSearch = useLocation().search;
			return null;
		};
		render(
			<MemoryRouter>
				<FlowHeadline />
				<LocationProbe />
			</MemoryRouter>,
		);

		fireEvent.click(screen.getByText("code/beats"));

		const params = new URLSearchParams(lastSearch);
		expect(params.get("repo")).toBe("/Users/me/code/beats");
	});

	it("clicks 'in <language>' to deep-link Insights pre-filtered by language", () => {
		let lastSearch = "";
		const LocationProbe = () => {
			lastSearch = useLocation().search;
			return null;
		};
		render(
			<MemoryRouter>
				<FlowHeadline />
				<LocationProbe />
			</MemoryRouter>,
		);

		fireEvent.click(screen.getByText("go"));

		const params = new URLSearchParams(lastSearch);
		expect(params.get("language")).toBe("go");
	});

	it("clicking a deep-link pill does not also trigger the card's own /insights link", () => {
		// The card wraps in a <Link to="/insights"> so clicking the
		// pill must call stopPropagation. Otherwise we'd navigate to
		// /insights (no filter) from the bubbled card click and then
		// to /insights?repo=… from the pill click — exact race
		// depends on the router internals, but neither outcome is
		// what the user wants. Verify the pill wins cleanly: search
		// string contains repo=, not empty.
		let lastSearch = "";
		const LocationProbe = () => {
			lastSearch = useLocation().search;
			return null;
		};
		render(
			<MemoryRouter>
				<FlowHeadline />
				<LocationProbe />
			</MemoryRouter>,
		);

		fireEvent.click(screen.getByText("code/beats"));
		// If propagation leaked, we'd see lastSearch === "" from the
		// card's bare /insights navigation. Asserting repo= is set
		// proves the pill click won, not the card.
		expect(lastSearch).toContain("repo=");
	});

	it("prefers today's slice over yesterday's when both have data", () => {
		// Avoid the bug class where the fallback wins even though
		// today has fresh data. Distinct numbers ensure unambiguous
		// assertion.
		setSummaries({
			today: makeSummary({ avg: 0.8, count: 5 }),
			yesterday: makeSummary({ avg: 0.3, count: 100 }),
		});
		renderWithRouter(<FlowHeadline />);
		expect(screen.getByText("Flow today")).toBeInTheDocument();
		expect(screen.getByText("80")).toBeInTheDocument();
		expect(screen.queryByText("30")).not.toBeInTheDocument();
	});
});
