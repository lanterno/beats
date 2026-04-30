/**
 * Render-level tests for FlowByLanguage's click-to-filter behavior.
 * Mirrors FlowByRepo.test.tsx — same shape, different axis.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FlowWindow } from "@/shared/api";
import { FlowByLanguage } from "./FlowByLanguage";

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
	// Two windows in Go, one in TypeScript — Go ranks first by count.
	vi.mocked(useFlowWindows).mockReturnValue({
		data: [
			makeWindow({ flow_score: 0.6, editor_language: "go" }),
			makeWindow({ flow_score: 0.8, editor_language: "go" }),
			makeWindow({ flow_score: 0.4, editor_language: "typescript" }),
		],
		// biome-ignore lint/suspicious/noExplicitAny: useQuery's full return shape is irrelevant here.
	} as any);
});

function rowFor(language: string): HTMLElement {
	return screen.getByTitle(language).closest("button") as HTMLElement;
}

describe("FlowByLanguage", () => {
	it("renders one row per language id", () => {
		render(<FlowByLanguage />);
		expect(rowFor("go")).toBeInTheDocument();
		expect(rowFor("typescript")).toBeInTheDocument();
	});

	it("calls onSelectLanguage with the raw language id when a row is clicked", () => {
		const onSelectLanguage = vi.fn();
		render(<FlowByLanguage onSelectLanguage={onSelectLanguage} />);

		fireEvent.click(rowFor("go"));

		expect(onSelectLanguage).toHaveBeenCalledTimes(1);
		// The card stores the raw language id even though the display
		// label may be prettier ("Go" / "TypeScript").
		expect(onSelectLanguage).toHaveBeenCalledWith("go");
	});

	it("clicking the active row clears the filter (toggle behavior)", () => {
		const onSelectLanguage = vi.fn();
		render(<FlowByLanguage selectedLanguage="go" onSelectLanguage={onSelectLanguage} />);

		fireEvent.click(rowFor("go"));

		expect(onSelectLanguage).toHaveBeenCalledWith(undefined);
	});

	it("marks the active row with aria-pressed=true", () => {
		render(<FlowByLanguage selectedLanguage="go" onSelectLanguage={() => {}} />);

		expect(rowFor("go")).toHaveAttribute("aria-pressed", "true");
		expect(rowFor("typescript")).toHaveAttribute("aria-pressed", "false");
	});

	it("renders nothing when there are no windows", () => {
		vi.mocked(useFlowWindows).mockReturnValueOnce({
			data: [],
			// biome-ignore lint/suspicious/noExplicitAny: see beforeEach.
		} as any);
		const { container } = render(<FlowByLanguage />);
		expect(container.firstChild).toBeNull();
	});
});
