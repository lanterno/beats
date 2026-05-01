/**
 * Render tests for FlowThisWeek. The contracts worth locking in:
 *
 * - Always renders 7 bars when there's any data (empty-day backfill).
 *   A missed day should read as a gap, not as bars sliding around to
 *   close the space. This is the behavior FlowThisWeek's docstring
 *   specifically calls out.
 * - The "Best day" peak annotation only renders when peak.count > 0
 *   (i.e. at least one populated day). Calling out a 0/100 "best day"
 *   when nothing has data reads as broken.
 * - Hides itself entirely when there are zero windows in the whole
 *   7-day window.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FlowWindow } from "@/shared/api";
import { FlowThisWeek } from "./FlowThisWeek";

vi.mock("@/entities/session", () => ({
	useFlowWindowsLastDays: vi.fn(),
}));

import { useFlowWindowsLastDays } from "@/entities/session";

afterEach(cleanup);

function makeWindow(overrides: Partial<FlowWindow> = {}): FlowWindow {
	return {
		id: Math.random().toString(36).slice(2),
		// Local-time string so localDateKey() returns a deterministic
		// YYYY-MM-DD that matches the test runner's clock interpretation.
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

function setWindows(windows: FlowWindow[] | undefined, isLoading = false) {
	vi.mocked(useFlowWindowsLastDays).mockReturnValue({
		data: windows,
		isLoading,
		// biome-ignore lint/suspicious/noExplicitAny: useQuery's full return shape is irrelevant here.
	} as any);
}

beforeEach(() => {
	setWindows(undefined);
});

describe("FlowThisWeek", () => {
	it("hides itself while loading", () => {
		setWindows(undefined, true);
		const { container } = render(<FlowThisWeek />);
		expect(container.firstChild).toBeNull();
	});

	it("hides itself when there are no windows in the whole 7-day window", () => {
		setWindows([]);
		const { container } = render(<FlowThisWeek />);
		expect(container.firstChild).toBeNull();
	});

	it("renders exactly 7 day bars even when only one day has data", () => {
		// Single window today. The card should backfill the other 6
		// days as no-data bars rather than collapse to 1 bar — keeping
		// the chart width constant so a missed day reads as a gap.
		const today = new Date();
		const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
		setWindows([makeWindow({ flow_score: 0.7, window_start: `${todayKey}T10:00:00` })]);

		render(<FlowThisWeek />);

		const chart = screen.getByRole("group", { name: "Daily flow score" });
		// Each bar is keyed/identified by its title attribute. Count the
		// elements that carry a title containing either "no data" or
		// "across N windows" — there should be exactly 7.
		const bars = chart.querySelectorAll("[title]");
		expect(bars.length).toBe(7);
	});

	it("annotates the peak day in the footer line", () => {
		const today = new Date();
		const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
		setWindows([
			makeWindow({ flow_score: 0.91, window_start: `${todayKey}T14:00:00` }),
			makeWindow({ flow_score: 0.5, window_start: `${todayKey}T10:00:00` }),
		]);
		render(<FlowThisWeek />);
		// Peak day is today (only populated day). Renders e.g. "Best
		// day this week: Wednesday at 70/100." across an avg.
		expect(screen.getByText(/Best day this week:/)).toBeInTheDocument();
	});

	it("does not render the peak annotation when no day actually has data", () => {
		// This is defensive — totalWindows === 0 already short-circuits
		// the whole component, so we'd never reach the peak branch with
		// a zero-count peak. But keep the assertion to lock in the
		// invariant: the "Best day this week" line only appears when
		// peak.count > 0, never as "Best day: Sunday at 0/100".
		setWindows([]);
		const { container } = render(<FlowThisWeek />);
		expect(container.firstChild).toBeNull();
		expect(screen.queryByText(/Best day this week/)).not.toBeInTheDocument();
	});
});
