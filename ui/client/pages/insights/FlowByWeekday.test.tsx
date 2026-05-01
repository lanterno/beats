/**
 * Render tests for FlowByWeekday. Locks in the MIN_WINDOWS_TO_RENDER
 * threshold (currently 50) — below that, weekday means are computed
 * from too few samples to be meaningful. Also covers the ISO Mon-first
 * display ordering and peak-weekday annotation.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FlowWindow } from "@/shared/api";
import { FlowByWeekday } from "./FlowByWeekday";

vi.mock("@/entities/session", () => ({
	useFlowWindowsLastDays: vi.fn(),
}));

import { useFlowWindowsLastDays } from "@/entities/session";

afterEach(cleanup);

function makeWindow(overrides: Partial<FlowWindow> = {}): FlowWindow {
	return {
		id: Math.random().toString(36).slice(2),
		// Local-time strings so getDay() is deterministic across timezones.
		window_start: "2026-04-27T09:00:00",
		window_end: "2026-04-27T09:01:00",
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
		// biome-ignore lint/suspicious/noExplicitAny: useQuery's full return shape is irrelevant.
	} as any);
}

beforeEach(() => {
	setWindows([]);
});

describe("FlowByWeekday", () => {
	it("hides itself while loading", () => {
		setWindows([], true);
		const { container } = render(<FlowByWeekday />);
		expect(container.firstChild).toBeNull();
	});

	it("hides itself when there are no windows", () => {
		const { container } = render(<FlowByWeekday />);
		expect(container.firstChild).toBeNull();
	});

	it("hides itself below the MIN_WINDOWS_TO_RENDER threshold", () => {
		// 49 windows total. Below the 50-minute floor — a 7-bar chart
		// drawn from one Monday + one Friday would be noise.
		const windows = Array.from({ length: 49 }, () =>
			makeWindow({ flow_score: 0.6, window_start: "2026-04-27T10:00:00" }),
		);
		setWindows(windows);
		const { container } = render(<FlowByWeekday />);
		expect(container.firstChild).toBeNull();
	});

	it("renders once the threshold is crossed and shows ISO weekday labels", () => {
		const windows = Array.from({ length: 60 }, (_, i) =>
			// Spread across 4 distinct weekdays (Mon-Thu).
			makeWindow({
				flow_score: 0.6,
				window_start: `2026-04-${27 + (i % 4)}T10:00:00`,
			}),
		);
		setWindows(windows);
		render(<FlowByWeekday />);
		expect(screen.getByText("Flow by weekday")).toBeInTheDocument();
		// Mon-first ISO ordering — different from JS getDay() Sunday-first.
		// Each label appears at least once (sometimes twice — chart cell
		// label plus a tooltip title). getAllByText handles either.
		for (const label of ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]) {
			expect(screen.getAllByText(label).length).toBeGreaterThan(0);
		}
	});

	it("annotates the peak weekday in the footer line", () => {
		// 2026-05-01 is Friday in local time. Friday windows score 0.9,
		// other days score 0.4 — the peak should be Friday.
		const windows: FlowWindow[] = [];
		for (let i = 0; i < 30; i++) {
			windows.push(makeWindow({ flow_score: 0.9, window_start: "2026-05-01T10:00:00" })); // Fri
		}
		for (let i = 0; i < 30; i++) {
			windows.push(makeWindow({ flow_score: 0.4, window_start: "2026-04-27T10:00:00" })); // Mon
		}
		setWindows(windows);
		render(<FlowByWeekday />);
		// "Best weekday over the last 28 days: Fri at …"
		const footer = screen.getByText(/Best weekday/);
		expect(footer.textContent).toMatch(/Fri/);
	});
});
