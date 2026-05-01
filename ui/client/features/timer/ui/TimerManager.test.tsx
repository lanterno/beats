/**
 * Tests for TimerManager — the timer card on the home page.
 *
 * Pin: start/stop button enablement, the toast-with-daily-avg
 * comparison after stopping, the toast fallback when the avg call
 * fails, the running indicator, the auto-select-from-initialProjectId
 * effect, and the time-input toggles.
 *
 * Mocks the useTimer hook and the timer API module so we can drive
 * the component into specific states without setting up the
 * underlying state machine. ProjectSelector renders as-is — keeps
 * the test honest about what the user actually sees.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProjectWithDuration } from "@/entities/project";

const toastSuccess = vi.fn();
vi.mock("sonner", () => ({
	toast: { success: (...args: unknown[]) => toastSuccess(...args) },
}));

const mockUseTimer = vi.fn();
vi.mock("../model", () => ({
	useTimer: () => mockUseTimer(),
}));

vi.mock("../api", () => ({
	fetchDailyAverage: vi.fn(),
}));

import { fetchDailyAverage } from "../api";
import { TimerManager } from "./TimerManager";

const PROJECTS: ProjectWithDuration[] = [
	{
		id: "p-alpha",
		name: "Alpha",
		description: "First project",
		color: "#5B9CF6",
		archived: false,
		goalOverrides: [],
		totalMinutes: 0,
		weeklyMinutes: 0,
	},
	{
		id: "p-beta",
		name: "Beta",
		color: "#34D399",
		archived: false,
		goalOverrides: [],
		totalMinutes: 0,
		weeklyMinutes: 0,
	},
];

function makeTimer(overrides: Partial<ReturnType<typeof defaultTimer>> = {}) {
	return { ...defaultTimer(), ...overrides };
}

function defaultTimer() {
	return {
		isRunning: false,
		selectedProjectId: null as string | null,
		elapsedSeconds: 0,
		customStartTime: null as string | null,
		startTimer: vi.fn(),
		stopTimer: vi.fn(),
		selectProject: vi.fn(),
		setCustomStartTime: vi.fn(),
	};
}

beforeEach(() => {
	mockUseTimer.mockReset();
	(fetchDailyAverage as ReturnType<typeof vi.fn>).mockReset();
	toastSuccess.mockReset();
});

afterEach(cleanup);

describe("TimerManager", () => {
	describe("button enablement", () => {
		it("Start is disabled with no project selected", () => {
			mockUseTimer.mockReturnValue(makeTimer());
			render(<TimerManager projects={PROJECTS} />);
			expect(screen.getByRole("button", { name: /^Start$/i })).toBeDisabled();
		});

		it("Start is enabled once a project is selected and timer not running", () => {
			mockUseTimer.mockReturnValue(makeTimer({ selectedProjectId: "p-alpha" }));
			render(<TimerManager projects={PROJECTS} />);
			expect(screen.getByRole("button", { name: /^Start$/i })).toBeEnabled();
		});

		it("Start is disabled while running (already running, can't double-start)", () => {
			mockUseTimer.mockReturnValue(
				makeTimer({ isRunning: true, selectedProjectId: "p-alpha", elapsedSeconds: 60 }),
			);
			render(<TimerManager projects={PROJECTS} />);
			expect(screen.getByRole("button", { name: /^Start$/i })).toBeDisabled();
		});

		it("Stop is disabled when not running", () => {
			mockUseTimer.mockReturnValue(makeTimer({ selectedProjectId: "p-alpha" }));
			render(<TimerManager projects={PROJECTS} />);
			expect(screen.getByRole("button", { name: /^Stop$/i })).toBeDisabled();
		});

		it("Stop is enabled while running", () => {
			mockUseTimer.mockReturnValue(
				makeTimer({ isRunning: true, selectedProjectId: "p-alpha", elapsedSeconds: 30 }),
			);
			render(<TimerManager projects={PROJECTS} />);
			expect(screen.getByRole("button", { name: /^Stop$/i })).toBeEnabled();
		});
	});

	describe("running indicator", () => {
		it("shows the Running pill when isRunning is true", () => {
			mockUseTimer.mockReturnValue(makeTimer({ isRunning: true, selectedProjectId: "p-alpha" }));
			render(<TimerManager projects={PROJECTS} />);
			expect(screen.getByText("Running")).toBeInTheDocument();
		});

		it("hides the Running pill when not running", () => {
			mockUseTimer.mockReturnValue(makeTimer({ selectedProjectId: "p-alpha" }));
			render(<TimerManager projects={PROJECTS} />);
			expect(screen.queryByText("Running")).not.toBeInTheDocument();
		});
	});

	describe("start", () => {
		it("calls startTimer with the selected project on click", async () => {
			const timer = makeTimer({ selectedProjectId: "p-alpha" });
			mockUseTimer.mockReturnValue(timer);
			render(<TimerManager projects={PROJECTS} />);
			await userEvent.click(screen.getByRole("button", { name: /^Start$/i }));
			expect(timer.startTimer).toHaveBeenCalledWith("p-alpha");
		});

		it("passes a customStartTime when set + the start-time input is open", async () => {
			const timer = makeTimer({
				selectedProjectId: "p-alpha",
				customStartTime: "2026-05-01T09:00:00.000Z",
			});
			mockUseTimer.mockReturnValue(timer);
			render(<TimerManager projects={PROJECTS} />);

			// Open the start-time panel.
			await userEvent.click(screen.getByRole("button", { name: /Set start time/i }));
			// Now click Start.
			await userEvent.click(screen.getByRole("button", { name: /^Start$/i }));
			expect(timer.startTimer).toHaveBeenCalledWith("p-alpha", "2026-05-01T09:00:00.000Z");
		});
	});

	describe("stop + toast", () => {
		it("toasts with daily-avg comparison when fetchDailyAverage has data", async () => {
			(fetchDailyAverage as ReturnType<typeof vi.fn>).mockResolvedValue({
				avg_minutes: 60,
				days_tracked: 5,
			});
			const timer = makeTimer({
				isRunning: true,
				selectedProjectId: "p-alpha",
				elapsedSeconds: 75 * 60, // 75 minutes — 25% above
			});
			mockUseTimer.mockReturnValue(timer);
			render(<TimerManager projects={PROJECTS} />);
			await userEvent.click(screen.getByRole("button", { name: /^Stop$/i }));

			expect(timer.stopTimer).toHaveBeenCalled();

			await vi.waitFor(() => {
				expect(toastSuccess).toHaveBeenCalledWith(
					"Logged 75m to Alpha — 25% above your daily avg (60m)",
				);
			});
		});

		it("toasts without comparison when days_tracked is zero", async () => {
			(fetchDailyAverage as ReturnType<typeof vi.fn>).mockResolvedValue({
				avg_minutes: 0,
				days_tracked: 0,
			});
			const timer = makeTimer({
				isRunning: true,
				selectedProjectId: "p-alpha",
				elapsedSeconds: 30 * 60,
			});
			mockUseTimer.mockReturnValue(timer);
			render(<TimerManager projects={PROJECTS} />);
			await userEvent.click(screen.getByRole("button", { name: /^Stop$/i }));

			await vi.waitFor(() => {
				expect(toastSuccess).toHaveBeenCalledWith("Logged 30m to Alpha");
			});
		});

		it("toasts with the plain fallback when fetchDailyAverage rejects", async () => {
			(fetchDailyAverage as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("network down"));
			const timer = makeTimer({
				isRunning: true,
				selectedProjectId: "p-alpha",
				elapsedSeconds: 5 * 60,
			});
			mockUseTimer.mockReturnValue(timer);
			render(<TimerManager projects={PROJECTS} />);
			await userEvent.click(screen.getByRole("button", { name: /^Stop$/i }));

			await vi.waitFor(() => {
				expect(toastSuccess).toHaveBeenCalledWith("Logged 5m to Alpha");
			});
		});

		it("invokes onSessionSaved after stopping", async () => {
			(fetchDailyAverage as ReturnType<typeof vi.fn>).mockResolvedValue({
				avg_minutes: 0,
				days_tracked: 0,
			});
			const onSaved = vi.fn();
			const timer = makeTimer({
				isRunning: true,
				selectedProjectId: "p-alpha",
				elapsedSeconds: 60,
			});
			mockUseTimer.mockReturnValue(timer);
			render(<TimerManager projects={PROJECTS} onSessionSaved={onSaved} />);
			await userEvent.click(screen.getByRole("button", { name: /^Stop$/i }));

			expect(onSaved).toHaveBeenCalled();
		});
	});

	describe("initialProjectId effect", () => {
		it("calls selectProject with initialProjectId when present in the list", () => {
			const timer = makeTimer();
			mockUseTimer.mockReturnValue(timer);
			render(<TimerManager projects={PROJECTS} initialProjectId="p-beta" />);
			expect(timer.selectProject).toHaveBeenCalledWith("p-beta");
		});

		it("does not call selectProject for an unknown initialProjectId", () => {
			const timer = makeTimer();
			mockUseTimer.mockReturnValue(timer);
			render(<TimerManager projects={PROJECTS} initialProjectId="p-doesnt-exist" />);
			expect(timer.selectProject).not.toHaveBeenCalled();
		});
	});

	describe("time-input toggles", () => {
		it("toggles the start-time input visibility", async () => {
			mockUseTimer.mockReturnValue(makeTimer({ selectedProjectId: "p-alpha" }));
			render(<TimerManager projects={PROJECTS} />);

			expect(screen.queryByLabelText(/Start time/i)).not.toBeInTheDocument();

			await userEvent.click(screen.getByRole("button", { name: /Set start time/i }));
			expect(screen.getByText("Start time")).toBeInTheDocument();

			await userEvent.click(screen.getByRole("button", { name: /Hide start time/i }));
			expect(screen.queryByText("Start time")).not.toBeInTheDocument();
		});

		it("renders the Set stop time toggle only while running", () => {
			// Not running → no toggle.
			mockUseTimer.mockReturnValue(makeTimer({ selectedProjectId: "p-alpha" }));
			const { unmount } = render(<TimerManager projects={PROJECTS} />);
			expect(screen.queryByRole("button", { name: /Set stop time/i })).not.toBeInTheDocument();
			unmount();
			cleanup();

			// Running → the toggle appears.
			mockUseTimer.mockReturnValue(
				makeTimer({ isRunning: true, selectedProjectId: "p-alpha", elapsedSeconds: 30 }),
			);
			render(<TimerManager projects={PROJECTS} />);
			expect(screen.getByRole("button", { name: /Set stop time/i })).toBeInTheDocument();
		});
	});

	describe("guards", () => {
		it("does nothing on Start when no project is selected", async () => {
			const timer = makeTimer();
			mockUseTimer.mockReturnValue(timer);
			render(<TimerManager projects={PROJECTS} />);

			// The button is disabled, but exercise the click path anyway —
			// userEvent.click respects disabled, so this confirms the guard
			// holds even if the disabled attribute were removed.
			const startBtn = screen.getByRole("button", { name: /^Start$/i });
			fireEvent.click(startBtn);
			expect(timer.startTimer).not.toHaveBeenCalled();
		});
	});
});
