import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DailyBrief } from "./DailyBrief";

const generateMutate = vi.fn();
const feedbackMutate = vi.fn();
const useCoachBriefMock = vi.fn();
const useCoachBriefHistoryMock = vi.fn();

vi.mock("@/entities/coach", () => ({
	useCoachBrief: () => useCoachBriefMock(),
	useCoachBriefHistory: () => useCoachBriefHistoryMock(),
	useGenerateBrief: () => ({ mutate: generateMutate, isPending: false }),
	useBriefFeedback: () => ({ mutate: feedbackMutate, isPending: false, isError: false }),
}));

const TODAY = { date: "2026-05-29", body: "today body" };
const HISTORY = [
	TODAY,
	{ date: "2026-05-28", body: "yesterday body" },
	{ date: "2026-05-27", body: "older body" },
];

describe("DailyBrief history", () => {
	beforeEach(() => {
		generateMutate.mockReset();
		useCoachBriefMock.mockReset();
		useCoachBriefHistoryMock.mockReset();
		useCoachBriefMock.mockReturnValue({ data: TODAY, isLoading: false });
		useCoachBriefHistoryMock.mockReturnValue({ data: HISTORY });
	});

	afterEach(cleanup);

	it("shows today's brief by default", () => {
		render(<DailyBrief />);
		expect(screen.getByText("today body")).toBeInTheDocument();
	});

	it("swaps to a past brief's body when its date is clicked", async () => {
		render(<DailyBrief />);
		await userEvent.click(screen.getByRole("button", { name: "2026-05-28" }));

		expect(screen.getByText("yesterday body")).toBeInTheDocument();
		expect(screen.getByText("Brief for 2026-05-28")).toBeInTheDocument();
		expect(screen.queryByText("today body")).not.toBeInTheDocument();
		// The selected chip is marked pressed for assistive tech.
		expect(screen.getByRole("button", { name: "2026-05-28" })).toHaveAttribute(
			"aria-pressed",
			"true",
		);
	});

	it("returns to today via the ← Today control", async () => {
		render(<DailyBrief />);
		await userEvent.click(screen.getByRole("button", { name: "2026-05-28" }));
		await userEvent.click(screen.getByRole("button", { name: "← Today" }));

		expect(screen.getByText("today body")).toBeInTheDocument();
		expect(screen.queryByText("yesterday body")).not.toBeInTheDocument();
	});

	it("toggles a selected date back to today when clicked again", async () => {
		render(<DailyBrief />);
		const chip = screen.getByRole("button", { name: "2026-05-28" });
		await userEvent.click(chip);
		expect(screen.getByText("yesterday body")).toBeInTheDocument();
		await userEvent.click(chip);
		expect(screen.getByText("today body")).toBeInTheDocument();
	});
});

describe("DailyBrief rating", () => {
	beforeEach(() => {
		feedbackMutate.mockReset();
		useCoachBriefHistoryMock.mockReturnValue({ data: HISTORY });
	});

	afterEach(cleanup);

	it("rates the brief on screen", async () => {
		useCoachBriefMock.mockReturnValue({ data: TODAY, isLoading: false });
		render(<DailyBrief />);
		await userEvent.click(screen.getByRole("button", { name: "Helpful" }));

		expect(feedbackMutate).toHaveBeenCalledWith({ date: "2026-05-29", rating: "helpful" });
	});

	it("clears a rating when the chosen one is picked again", async () => {
		useCoachBriefMock.mockReturnValue({
			data: { ...TODAY, feedback: "not_useful" },
			isLoading: false,
		});
		render(<DailyBrief />);
		const notUseful = screen.getByRole("button", { name: "Not useful" });
		expect(notUseful).toHaveAttribute("aria-pressed", "true");
		await userEvent.click(notUseful);

		expect(feedbackMutate).toHaveBeenCalledWith({ date: "2026-05-29", rating: null });
	});

	it("rates a past brief under its own date", async () => {
		useCoachBriefMock.mockReturnValue({ data: TODAY, isLoading: false });
		render(<DailyBrief />);
		await userEvent.click(screen.getByRole("button", { name: "2026-05-28" }));
		await userEvent.click(screen.getByRole("button", { name: "Not useful" }));

		expect(feedbackMutate).toHaveBeenCalledWith({ date: "2026-05-28", rating: "not_useful" });
	});
});
