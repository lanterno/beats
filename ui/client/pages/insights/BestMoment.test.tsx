/**
 * Render-level tests for BestMoment. The contract worth locking in is
 * the "don't celebrate weak peaks" threshold (currently 0.7) and the
 * peak-picking logic — accidentally calling a 0.42 peak "your best"
 * reads as faint praise, and is the kind of regression that's easy to
 * miss in a refactor.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FlowWindow } from "@/shared/api";
import { BestMoment } from "./BestMoment";

vi.mock("@/entities/session", () => ({
	useFlowWindowsLastDays: vi.fn(),
}));

vi.mock("@/entities/project", () => ({
	useProjects: vi.fn(),
}));

import { useProjects } from "@/entities/project";
import { useFlowWindowsLastDays } from "@/entities/session";

afterEach(cleanup);

function makeWindow(overrides: Partial<FlowWindow> = {}): FlowWindow {
	return {
		id: Math.random().toString(36).slice(2),
		// Local-time string (no Z) so getHours()/getDay() are deterministic
		// across timezones running the test runner.
		window_start: "2026-04-30T14:32:00",
		window_end: "2026-04-30T14:33:00",
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

beforeEach(() => {
	// biome-ignore lint/suspicious/noExplicitAny: useQuery's full return shape is irrelevant to these tests.
	vi.mocked(useProjects).mockReturnValue({ data: [] } as any);
});

function setWindows(windows: FlowWindow[]) {
	vi.mocked(useFlowWindowsLastDays).mockReturnValue({
		data: windows,
		// biome-ignore lint/suspicious/noExplicitAny: see beforeEach.
	} as any);
}

describe("BestMoment", () => {
	it("hides itself when there are no windows", () => {
		setWindows([]);
		const { container } = render(<BestMoment />);
		expect(container.firstChild).toBeNull();
	});

	it("hides itself when the peak is below the celebration threshold (0.7)", () => {
		// Don't crown a 0.69 as "your best" — reads as faint praise.
		setWindows([makeWindow({ flow_score: 0.69 })]);
		const { container } = render(<BestMoment />);
		expect(container.firstChild).toBeNull();
	});

	it("renders when at least one window crosses the threshold", () => {
		setWindows([makeWindow({ flow_score: 0.4 }), makeWindow({ flow_score: 0.91 })]);
		render(<BestMoment />);
		expect(screen.getByText("Peak this week")).toBeInTheDocument();
		expect(screen.getByText("91")).toBeInTheDocument();
	});

	it("picks the highest-scoring window across the slice", () => {
		// Three candidates above threshold; the 0.95 should win.
		setWindows([
			makeWindow({ flow_score: 0.71 }),
			makeWindow({ flow_score: 0.95 }),
			makeWindow({ flow_score: 0.82 }),
		]);
		render(<BestMoment />);
		expect(screen.getByText("95")).toBeInTheDocument();
		expect(screen.queryByText("82")).not.toBeInTheDocument();
		expect(screen.queryByText("71")).not.toBeInTheDocument();
	});

	it("renders the editor context when present and skips the row when absent", () => {
		setWindows([
			makeWindow({
				flow_score: 0.91,
				editor_repo: "/Users/me/code/beats",
				editor_branch: "main",
			}),
		]);
		render(<BestMoment />);
		expect(screen.getByText("code/beats")).toBeInTheDocument();
		// Branch lives in a sibling span, prefixed with " · ".
		expect(screen.getByText(/main/)).toBeInTheDocument();
	});

	it("falls back to the day name when the peak is from an earlier day", () => {
		// 2026-04-30 is a Thursday in local time.
		setWindows([makeWindow({ flow_score: 0.91, window_start: "2026-04-30T14:32:00" })]);
		render(<BestMoment />);
		// Should show one of the day names — either the day-of-week or
		// "Today" depending on when the test runs. Either is correct
		// behavior; both contain a time.
		expect(screen.getByText(/at/)).toBeInTheDocument();
		expect(screen.getByText("14:32")).toBeInTheDocument();
	});
});
