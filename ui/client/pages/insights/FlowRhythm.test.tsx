/**
 * Render tests for FlowRhythm. Locks in the MIN_WINDOWS_TO_RENDER
 * threshold (currently 12) — below that, hour-of-day means are too
 * noisy to plot, and rendering anyway would mislead. Also covers the
 * peak-hour annotation contract.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FlowWindow } from "@/shared/api";
import { FlowRhythm } from "./FlowRhythm";

vi.mock("@/entities/session", () => ({
	useFlowWindowsLastDays: vi.fn(),
}));

import { useFlowWindowsLastDays } from "@/entities/session";

afterEach(cleanup);

function makeWindow(overrides: Partial<FlowWindow> = {}): FlowWindow {
	return {
		id: Math.random().toString(36).slice(2),
		// Local-time string so getHours() is deterministic across timezones.
		window_start: "2026-04-30T09:00:00",
		window_end: "2026-04-30T09:01:00",
		flow_score: 0.5,
		cadence_score: 0.5,
		coherence_score: 0.5,
		category_fit_score: 0.5,
		idle_fraction: 0,
		dominant_bundle_id: "com.microsoft.VSCode",
		dominant_category: "coding",
		context_switches: 0,
		active_project_id: null,
		editor_repo: null,
		editor_branch: null,
		editor_language: null,
		...overrides,
	};
}

function setWindows(windows: FlowWindow[], isLoading = false) {
	vi.mocked(useFlowWindowsLastDays).mockReturnValue({
		data: windows,
		isLoading,
		// biome-ignore lint/suspicious/noExplicitAny: useQuery's full return shape is irrelevant here.
	} as any);
}

beforeEach(() => {
	setWindows([]);
});

describe("FlowRhythm", () => {
	it("hides itself while loading", () => {
		setWindows([], true);
		const { container } = render(<FlowRhythm />);
		expect(container.firstChild).toBeNull();
	});

	it("hides itself when there are no windows", () => {
		setWindows([]);
		const { container } = render(<FlowRhythm />);
		expect(container.firstChild).toBeNull();
	});

	it("hides itself below the MIN_WINDOWS_TO_RENDER threshold", () => {
		// 11 windows total — below the current 12-min floor. Rendering a
		// 24-bar chart from 11 minutes of data would draw a noisy
		// half-empty silhouette that misleads the user.
		const windows = Array.from({ length: 11 }, () =>
			makeWindow({ flow_score: 0.6, window_start: "2026-04-30T09:00:00" }),
		);
		setWindows(windows);
		const { container } = render(<FlowRhythm />);
		expect(container.firstChild).toBeNull();
	});

	it("renders once the threshold is crossed", () => {
		const windows = Array.from({ length: 12 }, (_, i) =>
			makeWindow({
				flow_score: 0.6,
				window_start: `2026-04-30T${String(9 + (i % 4)).padStart(2, "0")}:00:00`,
			}),
		);
		setWindows(windows);
		render(<FlowRhythm />);
		expect(screen.getByText("Flow rhythm")).toBeInTheDocument();
	});

	it("annotates the peak hour in the footer line", () => {
		// 14:00 windows score 0.9, others score 0.5 — peak hour is 14.
		const windows: FlowWindow[] = [];
		for (let i = 0; i < 8; i++) {
			windows.push(makeWindow({ flow_score: 0.9, window_start: "2026-04-30T14:00:00" }));
		}
		for (let i = 0; i < 8; i++) {
			windows.push(makeWindow({ flow_score: 0.5, window_start: "2026-04-30T09:00:00" }));
		}
		setWindows(windows);
		render(<FlowRhythm />);
		expect(screen.getByText(/14:00/)).toBeInTheDocument();
	});
});
