/**
 * Render-level tests for FlowByApp's click-to-filter behavior.
 * Mirrors FlowByRepo.test.tsx — same shape, bundle-id axis.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FlowWindow } from "@/shared/api";
import { FlowByApp } from "./FlowByApp";

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
	// Two windows in VS Code, one in Safari — VS Code wins by count.
	vi.mocked(useFlowWindows).mockReturnValue({
		data: [
			makeWindow({ flow_score: 0.8, dominant_bundle_id: "com.microsoft.VSCode" }),
			makeWindow({ flow_score: 0.7, dominant_bundle_id: "com.microsoft.VSCode" }),
			makeWindow({ flow_score: 0.3, dominant_bundle_id: "com.apple.Safari" }),
		],
		// biome-ignore lint/suspicious/noExplicitAny: useQuery's full return shape is irrelevant here.
	} as any);
});

function rowFor(bundleId: string): HTMLElement {
	return screen.getByTitle(bundleId).closest("button") as HTMLElement;
}

describe("FlowByApp", () => {
	it("renders one row per bundle id", () => {
		render(<FlowByApp />);
		expect(rowFor("com.microsoft.VSCode")).toBeInTheDocument();
		expect(rowFor("com.apple.Safari")).toBeInTheDocument();
	});

	it("calls onSelectBundleId with the full bundle id when a row is clicked", () => {
		const onSelectBundleId = vi.fn();
		render(<FlowByApp onSelectBundleId={onSelectBundleId} />);

		fireEvent.click(rowFor("com.microsoft.VSCode"));

		expect(onSelectBundleId).toHaveBeenCalledTimes(1);
		// Display label is "VS Code" but the filter uses the raw bundle id.
		expect(onSelectBundleId).toHaveBeenCalledWith("com.microsoft.VSCode");
	});

	it("clicking the active row clears the filter (toggle behavior)", () => {
		const onSelectBundleId = vi.fn();
		render(
			<FlowByApp selectedBundleId="com.microsoft.VSCode" onSelectBundleId={onSelectBundleId} />,
		);

		fireEvent.click(rowFor("com.microsoft.VSCode"));

		expect(onSelectBundleId).toHaveBeenCalledWith(undefined);
	});

	it("marks the active row with aria-pressed=true", () => {
		render(<FlowByApp selectedBundleId="com.microsoft.VSCode" onSelectBundleId={() => {}} />);

		expect(rowFor("com.microsoft.VSCode")).toHaveAttribute("aria-pressed", "true");
		expect(rowFor("com.apple.Safari")).toHaveAttribute("aria-pressed", "false");
	});

	it("renders nothing when there are no windows", () => {
		vi.mocked(useFlowWindows).mockReturnValueOnce({
			data: [],
			// biome-ignore lint/suspicious/noExplicitAny: see beforeEach.
		} as any);
		const { container } = render(<FlowByApp />);
		expect(container.firstChild).toBeNull();
	});
});
