/**
 * Tests for Layout — the authenticated app shell.
 *
 * Layout coordinates the timer, sync engine, command palette, and focus
 * mode. The tests here pin the contracts that only Layout owns:
 *
 * - the shell mounts (sidebar, mobile header, command palette, focus mode)
 * - timer props are passed through to both Sidebar and MobileHeader
 *   (a bug there means the sidebar shows stale state)
 *
 * Child components are stubbed to capture their props. The hooks are
 * mocked so we can drive Layout into specific states.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ── Mocks ──────────────────────────────────────────────────────────

const mockUseProjects = vi.fn();
vi.mock("@/entities/project", () => ({
	useProjects: () => mockUseProjects(),
	// Match the real export so consumers that filter archived (e.g. Layout's
	// activeProjects) work without re-mocking per test.
	visibleProjects: <T extends { archived: boolean }>(list: T[] | undefined) =>
		(list ?? []).filter((p) => !p.archived),
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
	FocusMode: () => <div data-testid="focus-mode" />,
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
	overrides: { timer?: Partial<ReturnType<typeof defaultTimer>>; projects?: typeof PROJECTS } = {},
) {
	mockUseTimer.mockReturnValue({ ...defaultTimer(), ...overrides.timer });
	mockUseProjects.mockReturnValue({ data: overrides.projects ?? PROJECTS });
}

beforeEach(() => {
	localStorage.clear();
	sidebarProps.mockReset();
	mobileHeaderProps.mockReset();
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
		it("mounts sidebar, mobile header, command palette, and focus mode", () => {
			setupHooks();
			renderLayout();
			expect(screen.getByTestId("sidebar")).toBeInTheDocument();
			expect(screen.getByTestId("mobile-header")).toBeInTheDocument();
			expect(screen.getByTestId("command-palette")).toBeInTheDocument();
			expect(screen.getByTestId("focus-mode")).toBeInTheDocument();
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
