/**
 * Render tests for FlowToday. Locks in the empty-state copy (this is
 * the prescribed user-facing guidance when the daemon isn't emitting),
 * the avg/peak/count surface, the BaselineDelta ±3 hide rule (same
 * regression class as FlowTrend's TrendDelta), and the peak-time link.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FlowWindow } from "@/shared/api";
import { FlowToday } from "./FlowToday";

vi.mock("@/entities/session", () => ({
	useFlowWindows: vi.fn(),
	useFlowWindowsLastDays: vi.fn(),
}));

import { useFlowWindows, useFlowWindowsLastDays } from "@/entities/session";

afterEach(cleanup);

function makeWindow(overrides: Partial<FlowWindow> = {}): FlowWindow {
	return {
		id: Math.random().toString(36).slice(2),
		// Local-time strings — getHours() is timezone-dependent and
		// running this test in a UTC and non-UTC runner would otherwise
		// produce different formatted times.
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

function setData(
	todayWindows: FlowWindow[] | undefined,
	baselineWindows: FlowWindow[] = [],
	isLoading = false,
) {
	vi.mocked(useFlowWindows).mockReturnValue({
		data: todayWindows,
		isLoading,
		// biome-ignore lint/suspicious/noExplicitAny: useQuery's full return shape is irrelevant here.
	} as any);
	vi.mocked(useFlowWindowsLastDays).mockReturnValue({
		data: baselineWindows,
		// biome-ignore lint/suspicious/noExplicitAny: see above.
	} as any);
}

beforeEach(() => {
	setData(undefined);
});

describe("FlowToday", () => {
	it("hides itself while loading", () => {
		setData(undefined, [], true);
		const { container } = render(<FlowToday />);
		expect(container.firstChild).toBeNull();
	});

	it("renders the empty-state copy when there are no windows today", () => {
		// User-facing guidance — pointing them at `beatsd run` is the
		// correct next step. Lock in the copy so a refactor doesn't
		// silently drop the actionable hint.
		setData([]);
		render(<FlowToday />);
		expect(screen.getByText(/No flow windows yet today/)).toBeInTheDocument();
		expect(screen.getByText("beatsd run")).toBeInTheDocument();
	});

	it("renders avg / peak / count when windows are present", () => {
		const windows = [
			makeWindow({ flow_score: 0.4 }),
			makeWindow({ flow_score: 0.8 }),
			makeWindow({ flow_score: 0.6 }),
		];
		setData(windows);
		render(<FlowToday />);
		// avg 0.6 → 60, peak 0.8 → 80, count 3
		expect(screen.getByText("60")).toBeInTheDocument();
		expect(screen.getByText("80")).toBeInTheDocument();
		expect(screen.getByText("3")).toBeInTheDocument();
	});

	it("hides the BaselineDelta when within ±3 score points", () => {
		// avg = 0.5, baseline (computed from 30+ baseline windows
		// strictly before today) = 0.51 → 1-point delta, below ±3.
		const today = [makeWindow({ flow_score: 0.5 })];
		const baseline = Array.from({ length: 40 }, (_, i) =>
			makeWindow({
				flow_score: 0.51,
				// Strictly before today's local date; flowBaseline keys by
				// localDateKey and excludes the current day.
				window_start: `2025-04-${String((i % 28) + 1).padStart(2, "0")}T10:00:00`,
			}),
		);
		setData(today, baseline);
		render(<FlowToday />);
		// No up/down arrow rendered.
		expect(screen.queryByText(/↑|↓/)).not.toBeInTheDocument();
	});

	it("surfaces the peak-time link when count > 1", () => {
		// Two windows; the highest-score one is at 14:32 local. The
		// "peak at HH:MM" link should appear and reflect that time.
		const windows = [
			makeWindow({ flow_score: 0.4, window_start: "2026-04-30T09:00:00" }),
			makeWindow({ flow_score: 0.91, window_start: "2026-04-30T14:32:00" }),
		];
		setData(windows);
		render(<FlowToday />);
		// Renders as a button so the user can click to seek the inspector.
		const link = screen.getByRole("button", { name: /14:32/ });
		expect(link).toBeInTheDocument();
	});

	it("does not crash on a single-window slice (peak-time link omitted)", () => {
		// count === 1 — peak time is trivially the only window, so
		// surfacing "peak at HH:MM" reads as filler. The component
		// should silently skip that row.
		setData([makeWindow({ flow_score: 0.7 })]);
		render(<FlowToday />);
		expect(screen.getByText("Flow today")).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: /peak at/ })).not.toBeInTheDocument();
	});

	it("clicking the peak-time link selects it and shows the inspector row", () => {
		const windows = [
			makeWindow({ flow_score: 0.4, window_start: "2026-04-30T09:00:00" }),
			makeWindow({
				flow_score: 0.91,
				window_start: "2026-04-30T14:32:00",
				editor_repo: "/Users/me/code/beats",
				editor_branch: "main",
			}),
		];
		setData(windows);
		render(<FlowToday />);

		fireEvent.click(screen.getByRole("button", { name: /14:32/ }));

		// Editor context surfaces on the inspector row of the selected
		// window. shortRepoPath collapses the path to "code/beats".
		expect(screen.getByText("code/beats")).toBeInTheDocument();
	});
});
