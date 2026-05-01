/**
 * Tests for Layout — the authenticated app shell.
 *
 * Layout pulls from a wide surface (7 entity hooks, 6 lib hooks, 7
 * child components). The tests here pin the *coordination* contracts
 * that only Layout owns:
 *
 * - applyRecurringIntentions runs at most once per day (localStorage
 *   key gates the effect; a second mount on the same day must not
 *   re-fire)
 * - timer props are passed through to both Sidebar and MobileHeader
 *   (a bug there means the sidebar shows stale state)
 * - todayTotalMinutes / todaySessionCount / topProject are computed
 *   correctly from the sessions data
 *
 * Child components are stubbed to capture their props. The hooks are
 * mocked so we can drive Layout into specific states.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ── Mocks ──────────────────────────────────────────────────────────

const applyRecurringIntentions = vi.fn();
vi.mock("@/entities/planning", () => ({
	applyRecurringIntentions: (...args: unknown[]) => applyRecurringIntentions(...args),
	useDailyNote: vi.fn(() => ({ data: undefined })),
	useIntentions: vi.fn(() => ({ data: [] })),
	useUpsertDailyNote: vi.fn(() => ({ mutate: vi.fn() })),
}));

const mockUseProjects = vi.fn();
vi.mock("@/entities/project", () => ({
	useProjects: () => mockUseProjects(),
}));

const mockUseTodaySessions = vi.fn();
const mockUseThisWeekSessions = vi.fn();
vi.mock("@/entities/session", () => ({
	useTodaySessions: () => mockUseTodaySessions(),
	useThisWeekSessions: () => mockUseThisWeekSessions(),
}));

const mockUseTimer = vi.fn();
vi.mock("@/features/timer", () => ({
	useTimer: () => mockUseTimer(),
}));

vi.mock("@/shared/lib", async () => {
	const actual = await vi.importActual<typeof import("@/shared/lib")>("@/shared/lib");
	return {
		...actual,
		useTheme: vi.fn(),
		useSyncEngine: vi.fn(),
		useFavicon: vi.fn(),
		useTimerNotification: vi.fn(),
		useKeyboardShortcuts: vi.fn(),
		useCommandActions: vi.fn(() => ({
			items: [],
			recencyBoost: vi.fn(),
			recordInvocation: vi.fn(),
		})),
	};
});

// Capture the props each child renders with so we can assert on them.
const sidebarProps = vi.fn();
const mobileHeaderProps = vi.fn();
const endOfDayProps = vi.fn();
vi.mock("@/widgets/sidebar", () => ({
	Sidebar: (props: Record<string, unknown>) => {
		sidebarProps(props);
		return <div data-testid="sidebar" />;
	},
	MobileHeader: (props: Record<string, unknown>) => {
		mobileHeaderProps(props);
		return <div data-testid="mobile-header" />;
	},
}));

vi.mock("@/shared/ui", () => ({
	CommandPalette: () => <div data-testid="command-palette" />,
	EndOfDayReview: (props: Record<string, unknown>) => {
		endOfDayProps(props);
		return <div data-testid="end-of-day" />;
	},
	FocusMode: () => <div data-testid="focus-mode" />,
	MorningBriefing: () => <div data-testid="morning-briefing" />,
	WeeklyReviewDialog: () => <div data-testid="weekly-review" />,
}));

import { Layout } from "./Layout";

// ── Helpers ────────────────────────────────────────────────────────

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

const PROJECTS = [
	{ id: "p1", name: "Alpha", color: "#5B9CF6", archived: false, goalOverrides: [] },
	{ id: "p2", name: "Beta", color: "#34D399", archived: false, goalOverrides: [] },
];

function setupHooks(
	overrides: {
		timer?: Partial<ReturnType<typeof defaultTimer>>;
		projects?: typeof PROJECTS;
		todaySessions?: Array<{ projectId?: string; duration: number; startTime: string }>;
		weekSessions?: Array<{ projectId?: string; duration: number; startTime: string }>;
	} = {},
) {
	mockUseTimer.mockReturnValue({ ...defaultTimer(), ...overrides.timer });
	mockUseProjects.mockReturnValue({ data: overrides.projects ?? PROJECTS });
	mockUseTodaySessions.mockReturnValue({ data: overrides.todaySessions ?? [] });
	mockUseThisWeekSessions.mockReturnValue({ data: overrides.weekSessions ?? [] });
}

beforeEach(() => {
	localStorage.clear();
	applyRecurringIntentions.mockReset();
	applyRecurringIntentions.mockResolvedValue(undefined);
	sidebarProps.mockReset();
	mobileHeaderProps.mockReset();
	endOfDayProps.mockReset();
});

afterEach(cleanup);

function renderLayout() {
	return render(
		<MemoryRouter>
			<Layout />
		</MemoryRouter>,
	);
}

// ── Tests ──────────────────────────────────────────────────────────

describe("Layout", () => {
	describe("renders the shell", () => {
		it("mounts sidebar, mobile header, and the dialog set", () => {
			setupHooks();
			renderLayout();
			expect(screen.getByTestId("sidebar")).toBeInTheDocument();
			expect(screen.getByTestId("mobile-header")).toBeInTheDocument();
			expect(screen.getByTestId("command-palette")).toBeInTheDocument();
			expect(screen.getByTestId("end-of-day")).toBeInTheDocument();
			expect(screen.getByTestId("morning-briefing")).toBeInTheDocument();
			expect(screen.getByTestId("weekly-review")).toBeInTheDocument();
			expect(screen.getByTestId("focus-mode")).toBeInTheDocument();
		});
	});

	describe("recurring intentions effect", () => {
		it("calls applyRecurringIntentions on first mount of the day", async () => {
			setupHooks();
			renderLayout();
			await vi.waitFor(() => {
				expect(applyRecurringIntentions).toHaveBeenCalledTimes(1);
			});
		});

		it("skips applyRecurringIntentions when today's key already exists", () => {
			const today = new Date().toISOString().slice(0, 10);
			localStorage.setItem("beats_recurring_applied", today);
			setupHooks();
			renderLayout();
			expect(applyRecurringIntentions).not.toHaveBeenCalled();
		});

		it("re-applies when the stored date is yesterday (the new-day case)", async () => {
			localStorage.setItem("beats_recurring_applied", "1999-01-01");
			setupHooks();
			renderLayout();
			await vi.waitFor(() => {
				expect(applyRecurringIntentions).toHaveBeenCalledTimes(1);
			});
		});

		it("writes today's key after a successful apply", async () => {
			setupHooks();
			renderLayout();
			const today = new Date().toISOString().slice(0, 10);
			await vi.waitFor(() => {
				expect(localStorage.getItem("beats_recurring_applied")).toBe(today);
			});
		});
	});

	describe("timer prop forwarding", () => {
		it("passes the same timer slice to Sidebar and MobileHeader", () => {
			const timer = {
				isRunning: true,
				selectedProjectId: "p1",
				elapsedSeconds: 1234,
				customStartTime: "2026-05-01T09:00:00.000Z",
			};
			setupHooks({ timer });
			renderLayout();

			const sidebar = sidebarProps.mock.calls[0][0];
			const mobile = mobileHeaderProps.mock.calls[0][0];

			expect(sidebar.isRunning).toBe(true);
			expect(sidebar.selectedProjectId).toBe("p1");
			expect(sidebar.elapsedSeconds).toBe(1234);
			expect(sidebar.customStartTime).toBe("2026-05-01T09:00:00.000Z");
			expect(sidebar.projects).toHaveLength(2);
			// MobileHeader gets the same shape — sidebar and header must
			// not drift apart.
			expect(mobile.isRunning).toBe(sidebar.isRunning);
			expect(mobile.selectedProjectId).toBe(sidebar.selectedProjectId);
			expect(mobile.elapsedSeconds).toBe(sidebar.elapsedSeconds);
			expect(mobile.projects).toEqual(sidebar.projects);
		});
	});

	describe("end-of-day review props", () => {
		it("computes total minutes and session count from todaySessions", () => {
			setupHooks({
				todaySessions: [
					{ projectId: "p1", duration: 30, startTime: "2026-05-01T09:00:00Z" },
					{ projectId: "p1", duration: 45, startTime: "2026-05-01T10:00:00Z" },
					{ projectId: "p2", duration: 15, startTime: "2026-05-01T11:00:00Z" },
				],
			});
			renderLayout();
			const props = endOfDayProps.mock.calls[0][0];
			expect(props.totalMinutesToday).toBe(90);
			expect(props.sessionCount).toBe(3);
		});

		it("picks the project with the most minutes today as the topProject", () => {
			// p1: 75 min total; p2: 15 min — p1 wins.
			setupHooks({
				todaySessions: [
					{ projectId: "p1", duration: 30, startTime: "2026-05-01T09:00:00Z" },
					{ projectId: "p1", duration: 45, startTime: "2026-05-01T10:00:00Z" },
					{ projectId: "p2", duration: 15, startTime: "2026-05-01T11:00:00Z" },
				],
			});
			renderLayout();
			expect(endOfDayProps.mock.calls[0][0].topProjectName).toBe("Alpha");
		});

		it("topProject is undefined when there are no sessions", () => {
			setupHooks({ todaySessions: [] });
			renderLayout();
			expect(endOfDayProps.mock.calls[0][0].topProjectName).toBeUndefined();
		});

		it("zero totals when no sessions", () => {
			setupHooks({ todaySessions: [] });
			renderLayout();
			const props = endOfDayProps.mock.calls[0][0];
			expect(props.totalMinutesToday).toBe(0);
			expect(props.sessionCount).toBe(0);
		});
	});

	describe("project filtering", () => {
		it("forwards the full projects list (not just active) to the sidebar", () => {
			// Sidebar shows archived projects in a separate section, so it
			// needs the full list. Active-only filtering is for keyboard
			// shortcut indexing, not for the sidebar.
			const projects = [
				{ id: "p1", name: "Active", color: "#000", archived: false, goalOverrides: [] },
				{ id: "p2", name: "Archived", color: "#111", archived: true, goalOverrides: [] },
			];
			setupHooks({ projects });
			renderLayout();
			const sidebar = sidebarProps.mock.calls[0][0];
			expect(sidebar.projects).toHaveLength(2);
			expect(sidebar.projects.map((p: { id: string }) => p.id)).toEqual(["p1", "p2"]);
		});
	});
});
