/**
 * The project page's regions per kind ("Where you stand", "Days", "Earlier
 * weeks"; the rail's Contract and Time off on a day job, Goal elsewhere), the
 * header's derived chip, the open week riding in the URL, and the booking
 * dialog opening from the standing on the right day. The panels' own
 * behaviour is pinned beside them (Standing, WeekDays, WeekLedger,
 * ContractRegister, TimeOff, AbsenceDialog tests).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { hooks } = vi.hoisted(() => ({
	hooks: {
		useProject: vi.fn(),
		useProjects: vi.fn(),
		useSessions: vi.fn(),
		useContractWeek: vi.fn(),
		useProjectLedger: vi.fn(),
		fetchTimerStatus: vi.fn(),
	},
}));

vi.mock("react-router", async () => {
	const actual = await vi.importActual<typeof import("react-router")>("react-router");
	return { ...actual, useParams: () => ({ projectId: "p1" }), useNavigate: () => vi.fn() };
});

vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	const idle = { mutateAsync: vi.fn(), mutate: vi.fn(), isPending: false };
	return {
		...actual,
		useProject: () => hooks.useProject(),
		useProjects: () => hooks.useProjects(),
		useContractWeek: (id: string, weekOf?: string, options?: unknown) =>
			hooks.useContractWeek(id, weekOf, options),
		useProjectLedger: (id: string, weeks?: number, options?: unknown) =>
			hooks.useProjectLedger(id, weeks, options),
		useUpdateProject: () => idle,
		useUpdateGoalOverrides: () => idle,
		useUpdateContract: () => idle,
		useArchiveProject: () => idle,
		useUnarchiveProject: () => idle,
		useHolidayRegions: () => ({ data: [] }),
		useProjectHolidays: () => ({ data: [] }),
	};
});

vi.mock("@/entities/absence", () => {
	const idle = { mutateAsync: vi.fn(), mutate: vi.fn(), isPending: false };
	return {
		useAbsences: () => ({ data: [], error: null }),
		useRecordAbsences: () => idle,
		useRemoveAbsences: () => idle,
		ABSENCE_TYPE_LABELS: { vacation: "Vacation", sick: "Sick", other: "Other" },
	};
});

vi.mock("@/entities/session", async () => {
	const actual = await vi.importActual<typeof import("@/entities/session")>("@/entities/session");
	const idle = { mutateAsync: vi.fn(), mutate: vi.fn(), isPending: false };
	return {
		...actual,
		useSessions: () => hooks.useSessions(),
		useUpdateSession: () => idle,
		useDeleteSession: () => idle,
	};
});

vi.mock("@/entities/planning", () => ({
	useProjectPlannedByWeek: () => ({ byMondayIso: new Map() }),
}));
vi.mock("@/entities/github", () => ({
	useProjectGitActivityByWeek: () => ({ byMondayIso: new Map() }),
	// ProjectGitHubBadge (a sibling component) reaches for this one.
	useGitHubStatus: () => ({ data: { connected: false }, isPending: false }),
}));
vi.mock("@/entities/intelligence", () => ({
	useProjectHealth: () => ({ data: [] }),
	useFocusScores: () => ({ data: [] }),
	useDismissInboxItem: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("@/features/timer", () => ({
	timerStatusKey: ["timer", "status"],
	fetchTimerStatus: () => hooks.fetchTimerStatus(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { addIsoDays, mondayOfIso, todayIso } from "@/shared/lib";
import ProjectDetails from "./ProjectDetails";

const PROJECT = {
	id: "p1",
	name: "Alpha",
	description: "the first one",
	color: "#d4952a",
	archived: false,
	goalOverrides: [],
	autostartRepos: [],
	kind: "side_project",
	totalMinutes: 600,
	weeklyMinutes: 0,
	weeklyGoal: 10,
};

const DAY_JOB = {
	...PROJECT,
	kind: "day_job",
	weeklyGoal: undefined,
	contract: {
		terms: [{ effectiveFrom: "2026-01-05", scheduleType: "custom", weeklyHours: 32 }],
		openingBalanceHours: 0,
	},
};

function LocationSpy() {
	const location = useLocation();
	return <output data-testid="location">{location.search}</output>;
}

function renderPage(entry = "/") {
	// Some children reach for the query client directly rather than through the
	// mocked hooks, so the provider has to be real.
	const client = new QueryClient({
		defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
	});
	return render(
		<QueryClientProvider client={client}>
			<MemoryRouter initialEntries={[entry]}>
				<ProjectDetails />
				<LocationSpy />
			</MemoryRouter>
		</QueryClientProvider>,
	);
}

beforeEach(() => {
	vi.clearAllMocks();
	hooks.useProject.mockReturnValue({ data: PROJECT, isLoading: false, error: null });
	hooks.useProjects.mockReturnValue({ data: [PROJECT] });
	hooks.useSessions.mockReturnValue({ data: [], refetch: vi.fn() });
	hooks.fetchTimerStatus.mockResolvedValue({ isBeating: false });
	hooks.useContractWeek.mockReturnValue({ data: undefined, isLoading: false, error: null });
	hooks.useProjectLedger.mockReturnValue({
		data: { since: null, totals: null, weeks: [] },
		isLoading: false,
		error: null,
	});
});

afterEach(cleanup);

describe("ProjectDetails", () => {
	it("shows a loading state while the project resolves", () => {
		hooks.useProject.mockReturnValue({ data: undefined, isLoading: true, error: null });
		renderPage();
		expect(screen.queryByText("the first one")).not.toBeInTheDocument();
	});

	it("renders the identity, the three regions and the Goal on a side project, without the contract surfaces", async () => {
		renderPage();
		expect(await screen.findByRole("button", { name: "Alpha" })).toBeInTheDocument();
		expect(screen.getByText("Side project · goal 10 h/week")).toBeInTheDocument();
		expect(screen.getByRole("region", { name: "Where you stand" })).toBeInTheDocument();
		expect(screen.getByRole("region", { name: "Days" })).toBeInTheDocument();
		expect(screen.getByRole("region", { name: "Earlier weeks" })).toBeInTheDocument();
		expect(screen.getByRole("region", { name: "Goal" })).toBeInTheDocument();
		expect(screen.queryByRole("region", { name: "Contract" })).not.toBeInTheDocument();
		expect(screen.queryByRole("region", { name: "Time off" })).not.toBeInTheDocument();
		expect(
			screen.getByText("No sessions yet — start the timer in the sidebar."),
		).toBeInTheDocument();
	});

	it("shows the contract surfaces on a day job, and the region caveat until a region is set", async () => {
		hooks.useProject.mockReturnValue({ data: DAY_JOB, isLoading: false, error: null });
		hooks.useContractWeek.mockReturnValue({
			data: {
				weekOf: mondayOfIso(todayIso()),
				expected: 25.6,
				worked: 12,
				remaining: 13.6,
				balance: 3,
				balanceAsOf: todayIso(),
				balanceOpening: 0,
				balanceWorked: 100,
				balanceExpectedThrough: 97,
				days: [],
			},
			isLoading: false,
			error: null,
		});
		renderPage();

		expect(await screen.findByText("Day job · 32 h/week")).toBeInTheDocument();
		const standing = screen.getByRole("region", { name: "Where you stand" });
		expect(within(standing).getByText("+3.0 h")).toBeInTheDocument();
		expect(within(standing).getByText("Expected").nextElementSibling).toHaveTextContent("25.6 h");
		expect(standing).toHaveTextContent("Public holidays are not deducted");
		expect(screen.getByRole("region", { name: "Contract" })).toBeInTheDocument();
		expect(screen.getByRole("region", { name: "Time off" })).toBeInTheDocument();
		expect(screen.queryByRole("region", { name: "Goal" })).not.toBeInTheDocument();
	});

	it("opens the booking dialog from the standing on the next day the contract expects hours", async () => {
		hooks.useProject.mockReturnValue({ data: DAY_JOB, isLoading: false, error: null });
		const thisMonday = mondayOfIso(todayIso());
		const nextMonday = addIsoDays(thisMonday, 7);
		// Due today and nothing after it this week; next week, Wednesday alone.
		const todayIndex = (new Date(`${todayIso()}T12:00:00`).getDay() + 6) % 7;
		const week = (weekOf: string, dueDay: number) => ({
			weekOf,
			expected: 6.4,
			worked: 0,
			remaining: 6.4,
			balance: 0,
			balanceAsOf: todayIso(),
			balanceOpening: 0,
			balanceWorked: 0,
			balanceExpectedThrough: 0,
			days: [0, 1, 2, 3, 4, 5, 6].map((i) => ({
				date: addIsoDays(weekOf, i),
				expected: i === dueDay ? 6.4 : 0,
				worked: 0,
			})),
		});
		hooks.useContractWeek.mockImplementation((_id: string, weekOf?: string) => ({
			data: weekOf === nextMonday ? week(nextMonday, 2) : week(weekOf ?? thisMonday, todayIndex),
			isLoading: false,
			error: null,
		}));
		renderPage();

		const standing = await screen.findByRole("region", { name: "Where you stand" });
		await userEvent.click(within(standing).getByRole("button", { name: "Book time off" }));
		const dialog = screen.getByRole("dialog", { name: "Book time off" });
		expect(within(dialog).getByLabelText("From")).toHaveValue(addIsoDays(nextMonday, 2));
	});

	it("puts the open week in the URL from ‹ › and drops it on Today", async () => {
		renderPage();
		await screen.findByRole("region", { name: "Days" });
		expect(screen.getByTestId("location")).toHaveTextContent("");

		await userEvent.click(screen.getByRole("button", { name: "Previous week" }));
		const lastMonday = mondayOfIso(todayIso());
		const d = new Date(`${lastMonday}T12:00:00`);
		d.setDate(d.getDate() - 7);
		const previous = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
		expect(screen.getByTestId("location")).toHaveTextContent(`?week=${previous}`);
		expect(hooks.useContractWeek).toHaveBeenCalledWith("p1", previous, expect.anything());

		await userEvent.click(screen.getByRole("button", { name: "Today" }));
		expect(screen.getByTestId("location")).toHaveTextContent("");
	});

	it("opens the week of any day named in ?week=, and this week for a malformed one", async () => {
		const twoWeeksBack = addIsoDays(mondayOfIso(todayIso()), -14);
		renderPage(`/?week=${addIsoDays(twoWeeksBack, 3)}`);
		await screen.findByRole("region", { name: "Days" });
		expect(hooks.useContractWeek).toHaveBeenCalledWith("p1", twoWeeksBack, expect.anything());
		expect(screen.getByRole("button", { name: "Today" })).toBeInTheDocument();
		cleanup();

		renderPage("/?week=garbage");
		await screen.findByRole("region", { name: "Days" });
		expect(screen.queryByRole("button", { name: "Today" })).not.toBeInTheDocument();
	});

	it("polls the current week and the ledger only while a beat runs on this project", async () => {
		renderPage();
		await screen.findByRole("region", { name: "Days" });
		expect(hooks.useProjectLedger).toHaveBeenLastCalledWith("p1", 8, { refetchInterval: false });
		cleanup();

		hooks.fetchTimerStatus.mockResolvedValue({
			isBeating: true,
			since: new Date().toISOString(),
			project: { id: "p1" },
		});
		renderPage();
		await waitFor(() =>
			expect(hooks.useProjectLedger).toHaveBeenLastCalledWith("p1", 8, { refetchInterval: 60_000 }),
		);
		expect(hooks.useContractWeek).toHaveBeenCalledWith("p1", mondayOfIso(todayIso()), {
			enabled: false,
			refetchInterval: 60_000,
		});
	});
});
