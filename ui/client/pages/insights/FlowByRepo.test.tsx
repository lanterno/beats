/**
 * Render-level tests for FlowByRepo's click-to-filter behavior.
 *
 * The aggregation logic is exercised by flowAggregation.test.ts; this
 * file locks in the user-facing interaction the card adds on top:
 * clicking a row → onSelectRepo, clicking the active row → undefined
 * (toggle clear), and aria-pressed reflecting the selected state.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FlowWindow } from "@/shared/api";
import { FlowByRepo } from "./FlowByRepo";

vi.mock("@/entities/session", () => ({
	useFlowWindows: vi.fn(),
}));

import { useFlowWindows } from "@/entities/session";

afterEach(cleanup);

function makeWindow(overrides: Partial<FlowWindow> = {}): FlowWindow {
	return {
		id: Math.random().toString(36).slice(2),
		window_start: "2026-04-30T09:00:00Z",
		window_end: "2026-04-30T09:01:00Z",
		flow_score: 0.5,
		cadence_score: 0.5,
		coherence_score: 0.5,
		category_fit_score: 0.5,
		idle_fraction: 0,
		dominant_bundle_id: "com.microsoft.VSCode",
		dominant_category: "coding",
		context_switches: 0,
		active_project_id: null,
		editor_repo: "/Users/me/code/beats",
		editor_branch: "main",
		editor_language: "go",
		...overrides,
	};
}

beforeEach(() => {
	// Default mock: two repos, beats with two windows (so it's the
	// "biggest" bucket), other with one. Each test can re-stub.
	vi.mocked(useFlowWindows).mockReturnValue({
		data: [
			makeWindow({ flow_score: 0.6, editor_repo: "/Users/me/code/beats" }),
			makeWindow({ flow_score: 0.8, editor_repo: "/Users/me/code/beats" }),
			makeWindow({ flow_score: 0.4, editor_repo: "/Users/me/code/other" }),
		],
		// biome-ignore lint/suspicious/noExplicitAny: useQuery's full return shape is irrelevant to these tests.
	} as any);
});

// Lookup helpers — the trailing "Best flow today on …" sentence in the
// card uses the same shortened repo string, so getByText finds two
// matches. Querying by the row buttons' title attribute (the FULL path)
// is unambiguous and matches what we actually want to act on.
function rowFor(repo: string): HTMLElement {
	return screen.getByTitle(repo).closest("button") as HTMLElement;
}

describe("FlowByRepo", () => {
	it("renders one row per repo with the trailing path segments", () => {
		render(<FlowByRepo />);
		expect(rowFor("/Users/me/code/beats")).toBeInTheDocument();
		expect(rowFor("/Users/me/code/other")).toBeInTheDocument();
	});

	it("calls onSelectRepo with the full repo path when a row is clicked", () => {
		const onSelectRepo = vi.fn();
		render(<FlowByRepo onSelectRepo={onSelectRepo} />);

		fireEvent.click(rowFor("/Users/me/code/beats"));

		expect(onSelectRepo).toHaveBeenCalledTimes(1);
		// The card stores and passes the full path; only the display is shortened.
		expect(onSelectRepo).toHaveBeenCalledWith("/Users/me/code/beats");
	});

	it("clicking the active row clears the filter (toggle behavior)", () => {
		const onSelectRepo = vi.fn();
		render(<FlowByRepo selectedRepo="/Users/me/code/beats" onSelectRepo={onSelectRepo} />);

		fireEvent.click(rowFor("/Users/me/code/beats"));

		expect(onSelectRepo).toHaveBeenCalledWith(undefined);
	});

	it("marks the active row with aria-pressed=true", () => {
		render(<FlowByRepo selectedRepo="/Users/me/code/beats" onSelectRepo={() => {}} />);

		expect(rowFor("/Users/me/code/beats")).toHaveAttribute("aria-pressed", "true");
		expect(rowFor("/Users/me/code/other")).toHaveAttribute("aria-pressed", "false");
	});

	it("does not throw when onSelectRepo is omitted (read-only mode)", () => {
		render(<FlowByRepo />);
		// No explicit assertion needed — clicking should be a no-op, not crash.
		fireEvent.click(rowFor("/Users/me/code/beats"));
	});

	it("renders nothing when there are no windows", () => {
		vi.mocked(useFlowWindows).mockReturnValueOnce({
			data: [],
			// biome-ignore lint/suspicious/noExplicitAny: see beforeEach.
		} as any);
		const { container } = render(<FlowByRepo />);
		expect(container.firstChild).toBeNull();
	});
});
