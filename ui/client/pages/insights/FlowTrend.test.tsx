/**
 * Render tests for FlowTrend. Locks in the two thresholds the card
 * relies on so a future refactor can't silently start drawing
 * misleading lines:
 *
 * - MIN_WEEKS_TO_RENDER = 4 — drawing 12 weeks of trend with one
 *   week of history reads as "you've been declining for 3 months"
 *   when really there's just no data.
 * - TrendDelta hidden under ±3 score points — 12 weekly means are
 *   noisy enough that a small delta doesn't signal direction.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FlowTrend } from "./FlowTrend";

vi.mock("@/entities/session", () => ({
	useWeeklyFlowTrend: vi.fn(),
}));

import { useWeeklyFlowTrend } from "@/entities/session";

afterEach(cleanup);

interface Pt {
	weekStart: string;
	avg: number;
	count: number;
}

function setPoints(points: Pt[] | undefined, isLoading = false) {
	vi.mocked(useWeeklyFlowTrend).mockReturnValue({
		data: points,
		isLoading,
		// biome-ignore lint/suspicious/noExplicitAny: useQuery's full return shape is irrelevant here.
	} as any);
}

beforeEach(() => {
	setPoints(undefined);
});

describe("FlowTrend", () => {
	it("hides itself while loading", () => {
		setPoints(undefined, true);
		const { container } = render(<FlowTrend />);
		expect(container.firstChild).toBeNull();
	});

	it("hides itself when there are no points", () => {
		setPoints([]);
		const { container } = render(<FlowTrend />);
		expect(container.firstChild).toBeNull();
	});

	it("hides itself when fewer than 4 weeks of data are populated", () => {
		// 3 populated weeks among 12 total — below the 4-week floor.
		// Mostly empty + 3 sparse weeks would draw a misleading line.
		const points: Pt[] = Array.from({ length: 12 }, (_, i) => ({
			weekStart: `2026-${String(i + 1).padStart(2, "0")}-01`,
			avg: i < 3 ? 0.6 : 0,
			count: i < 3 ? 50 : 0,
		}));
		setPoints(points);
		const { container } = render(<FlowTrend />);
		expect(container.firstChild).toBeNull();
	});

	it("renders once 4+ weeks are populated", () => {
		const points: Pt[] = Array.from({ length: 12 }, (_, i) => ({
			weekStart: `2026-${String(i + 1).padStart(2, "0")}-01`,
			avg: 0.6,
			count: 50,
		}));
		setPoints(points);
		render(<FlowTrend />);
		expect(screen.getByText("Flow trend")).toBeInTheDocument();
		expect(screen.getByText("last 12 weeks")).toBeInTheDocument();
	});

	it("hides the delta indicator when within ±3 score points", () => {
		// avg drifts from 0.60 to 0.62 — a 2-point delta is below the
		// ±3 threshold, so we shouldn't surface a direction arrow.
		const points: Pt[] = [
			{ weekStart: "2026-02-02", avg: 0.6, count: 50 },
			{ weekStart: "2026-02-09", avg: 0.6, count: 50 },
			{ weekStart: "2026-02-16", avg: 0.6, count: 50 },
			{ weekStart: "2026-02-23", avg: 0.62, count: 50 },
		];
		setPoints(points);
		render(<FlowTrend />);
		// No up-arrow; no down-arrow. The component renders these as
		// "↑ N" / "↓ N" strings, so checking for the arrow itself is
		// sufficient.
		expect(screen.queryByText(/↑|↓/)).not.toBeInTheDocument();
	});

	it("shows an up-arrow when the delta is at least +3", () => {
		const points: Pt[] = [
			{ weekStart: "2026-02-02", avg: 0.5, count: 50 },
			{ weekStart: "2026-02-09", avg: 0.55, count: 50 },
			{ weekStart: "2026-02-16", avg: 0.6, count: 50 },
			{ weekStart: "2026-02-23", avg: 0.7, count: 50 }, // +20 from week 1
		];
		setPoints(points);
		render(<FlowTrend />);
		expect(screen.getByText(/↑/)).toBeInTheDocument();
	});

	it("shows a down-arrow when the delta is at least -3", () => {
		const points: Pt[] = [
			{ weekStart: "2026-02-02", avg: 0.7, count: 50 },
			{ weekStart: "2026-02-09", avg: 0.65, count: 50 },
			{ weekStart: "2026-02-16", avg: 0.6, count: 50 },
			{ weekStart: "2026-02-23", avg: 0.5, count: 50 }, // -20 from week 1
		];
		setPoints(points);
		render(<FlowTrend />);
		expect(screen.getByText(/↓/)).toBeInTheDocument();
	});
});
