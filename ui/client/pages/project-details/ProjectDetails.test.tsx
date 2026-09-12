/**
 * Smoke coverage for the project page.
 *
 * This is the one genuinely monolithic component left in the UI — ~900 lines
 * in a single function — and it had no tests, which is exactly why splitting it
 * was unsafe. These cases pin what the page promises before that happens:
 * the week table, the session list, its pagination, and the week-scoping that
 * links the two.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { hooks } = vi.hoisted(() => ({
	hooks: {
		useProject: vi.fn(),
		useProjects: vi.fn(),
		useSessions: vi.fn(),
		useProjectWeeks: vi.fn(),
		useContractWeek: vi.fn(),
		useProjectPlannedByWeek: vi.fn(),
		useProjectGitActivityByWeek: vi.fn(),
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
		useProjectWeeks: () => hooks.useProjectWeeks(),
		useContractWeek: () => hooks.useContractWeek(),
		useUpdateProject: () => idle,
		useUpdateGoalOverrides: () => idle,
		useUpdateContract: () => idle,
		useHolidayRegions: () => ({ data: [] }),
		useProjectHolidays: () => ({ data: [] }),
	};
});

vi.mock("@/entities/absence", () => {
	const idle = { mutateAsync: vi.fn(), mutate: vi.fn(), isPending: false };
	return {
		useAbsences: () => ({ data: [], error: null }),
		useRecordAbsence: () => idle,
		useRemoveAbsence: () => idle,
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
	useProjectPlannedByWeek: () => hooks.useProjectPlannedByWeek(),
}));
vi.mock("@/entities/github", () => ({
	useProjectGitActivityByWeek: () => hooks.useProjectGitActivityByWeek(),
	// ProjectGitHubBadge (a sibling component) reaches for this one.
	useGitHubStatus: () => ({ data: { connected: false }, isPending: false }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import ProjectDetails from "./ProjectDetails";
import { getMondayIsoFor } from "./weekIso";

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
	weeklyGoal: 10,
};

function session(id: string, startIso: string, minutes: number) {
	const start = new Date(startIso);
	return {
		id,
		projectId: "p1",
		startTime: start.toISOString(),
		endTime: new Date(start.getTime() + minutes * 60_000).toISOString(),
		duration: minutes,
		note: "",
		tags: [],
	};
}

/** `days` after an ISO date, as ISO. */
function isoDaysAfter(iso: string, days: number): string {
	const d = new Date(`${iso}T12:00:00`);
	d.setDate(d.getDate() + days);
	const mm = String(d.getMonth() + 1).padStart(2, "0");
	const dd = String(d.getDate()).padStart(2, "0");
	return `${d.getFullYear()}-${mm}-${dd}`;
}

function renderPage() {
	// Some children reach for the query client directly rather than through the
	// mocked hooks, so the provider has to be real.
	const client = new QueryClient({
		defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
	});
	return render(
		<QueryClientProvider client={client}>
			<MemoryRouter>
				<ProjectDetails />
			</MemoryRouter>
		</QueryClientProvider>,
	);
}

beforeEach(() => {
	vi.clearAllMocks();
	hooks.useProject.mockReturnValue({ data: PROJECT, isLoading: false, error: null });
	hooks.useProjects.mockReturnValue({ data: [PROJECT] });
	hooks.useSessions.mockReturnValue({ data: [], refetch: vi.fn() });
	hooks.useProjectWeeks.mockReturnValue({ data: [] });
	hooks.useContractWeek.mockReturnValue({ data: undefined, isLoading: false, error: null });
	// Both hooks hand back a Map keyed by Monday ISO, not a plain object.
	hooks.useProjectPlannedByWeek.mockReturnValue({ byMondayIso: new Map() });
	hooks.useProjectGitActivityByWeek.mockReturnValue({ byMondayIso: new Map() });
});

afterEach(cleanup);

describe("ProjectDetails", () => {
	it("renders the project name", async () => {
		renderPage();
		expect(await screen.findAllByText("Alpha")).not.toHaveLength(0);
	});

	it("shows a loading state while the project resolves", () => {
		hooks.useProject.mockReturnValue({ data: undefined, isLoading: true, error: null });
		renderPage();
		expect(screen.queryByText("the first one")).not.toBeInTheDocument();
	});

	it("renders the week history and sessions sections", async () => {
		renderPage();
		expect(await screen.findByRole("region", { name: /week history/i })).toBeInTheDocument();
		expect(screen.getByRole("heading", { name: /sessions/i })).toBeInTheDocument();
	});

	it("lists the project's sessions", async () => {
		hooks.useSessions.mockReturnValue({
			data: [session("s1", "2026-04-27T09:00:00Z", 60), session("s2", "2026-04-27T14:00:00Z", 30)],
			refetch: vi.fn(),
		});
		renderPage();

		const sessions = await screen.findByRole("region", { name: /sessions/i });
		expect(
			within(sessions).getAllByRole("button", { name: /edit|delete/i }).length,
		).toBeGreaterThan(0);
	});

	it("paginates long session lists behind a show-more control", async () => {
		hooks.useSessions.mockReturnValue({
			data: Array.from({ length: 30 }, (_, i) =>
				session(`s${i}`, `2026-04-${String((i % 27) + 1).padStart(2, "0")}T09:00:00Z`, 30),
			),
			refetch: vi.fn(),
		});
		renderPage();

		const more = await screen.findByRole("button", { name: /more sessions/i });
		await userEvent.click(more);
		// The control either reveals the rest and disappears, or offers another page.
		expect(screen.queryByRole("button", { name: /more sessions/i })).not.toBe(more);
	});

	it("shows an empty state when the project has no sessions", async () => {
		renderPage();
		const sessions = await screen.findByRole("region", { name: /sessions/i });
		expect(within(sessions).queryAllByRole("button", { name: /^edit$/i })).toHaveLength(0);
	});

	it("shows the contract surfaces on a day job, and the region nudge until a region is set", async () => {
		hooks.useProject.mockReturnValue({
			data: {
				...PROJECT,
				kind: "day_job",
				contract: {
					terms: [{ effectiveFrom: "2026-01-05", scheduleType: "custom", weeklyHours: 32 }],
					openingBalanceHours: 0,
				},
			},
			isLoading: false,
			error: null,
		});
		renderPage();
		expect(await screen.findByText(/Complete your contract/)).toBeInTheDocument();
		expect(screen.getByRole("region", { name: /Contract history/i })).toBeInTheDocument();
		expect(screen.getByRole("region", { name: /Absences/i })).toBeInTheDocument();
		// A custom term owes hours, so the contract is the goal: the header
		// offers no way to a personal goal the settings form would not show.
		expect(screen.queryByTitle("Edit weekly goal")).not.toBeInTheDocument();
		expect(screen.queryByText("+ Set weekly goal")).not.toBeInTheDocument();
	});

	it("keeps the contract surfaces off a side project", async () => {
		renderPage();
		await screen.findAllByText("Alpha");
		expect(screen.queryByText(/Complete your contract/)).not.toBeInTheDocument();
		expect(screen.queryByRole("region", { name: /Contract history/i })).not.toBeInTheDocument();
		expect(screen.queryByRole("region", { name: /Absences/i })).not.toBeInTheDocument();
		expect(screen.queryByRole("region", { name: /against the contract/i })).not.toBeInTheDocument();
		expect(screen.getByTitle("Edit weekly goal")).toBeInTheDocument();
		// The personal goal's week can be overridden from the table.
		const history = screen.getByRole("region", { name: /week history/i });
		expect(within(history).getAllByTitle(/goal override/).length).toBeGreaterThan(0);
	});

	it("reads the header from the contract week and offers no goal override on a week the contract governs", async () => {
		hooks.useProject.mockReturnValue({
			data: {
				...PROJECT,
				kind: "day_job",
				// The API clears the personal goal on such a project; the contract is the goal.
				weeklyGoal: undefined,
				contract: {
					terms: [{ effectiveFrom: "2026-01-05", scheduleType: "custom", weeklyHours: 32 }],
					holidayCountry: "CH",
					openingBalanceHours: 0,
				},
			},
			isLoading: false,
			error: null,
		});
		// The week route reports the term's nominal hours as the effective goal,
		// for the current week and for a past one the same term governed.
		hooks.useProjectWeeks.mockReturnValue({
			data: [
				{
					weeksAgo: 0,
					hours: 0,
					dailyDurations: {},
					effectiveGoal: 32,
					effectiveGoalType: "target",
					effectiveGoalOverridden: false,
				},
				{
					weeksAgo: 1,
					weekStart: "2026-08-31",
					hours: 8,
					dailyDurations: {},
					effectiveGoal: 32,
					effectiveGoalType: "target",
					effectiveGoalOverridden: false,
				},
			],
		});
		// The contract week reports the expectation adjusted for a holiday.
		hooks.useContractWeek.mockReturnValue({
			data: {
				weekOf: "2026-09-07",
				expected: 25.6,
				worked: 12,
				remaining: 13.6,
				balance: 3,
				days: [],
			},
			isLoading: false,
			error: null,
		});
		renderPage();

		expect(await screen.findByTitle("This week against the contract")).toHaveTextContent(
			"12.0/25.6h",
		);
		expect(screen.getByRole("region", { name: /against the contract/i })).toBeInTheDocument();

		const history = screen.getByRole("region", { name: /week history/i });
		expect(within(history).getByText("—/32h").closest("button")).toBeNull();
		expect(within(history).getByText("8.0/32h").closest("button")).toBeNull();
		expect(within(history).queryByTitle(/goal override/)).not.toBeInTheDocument();
	});

	it("shows a governed week's expectation after holidays and absences in the history row", async () => {
		hooks.useProject.mockReturnValue({
			data: {
				...PROJECT,
				kind: "day_job",
				weeklyGoal: undefined,
				contract: {
					terms: [{ effectiveFrom: "2026-01-05", scheduleType: "custom", weeklyHours: 32 }],
					holidayCountry: "CH",
					openingBalanceHours: 0,
				},
			},
			isLoading: false,
			error: null,
		});
		// The /week/ route reports the term's nominal 32 as the goal and, beside
		// it, what the week expects once a day of vacation (this week) and a
		// holiday (last week) are off. The row must show the latter: it is the
		// figure the week card above it shows.
		hooks.useProjectWeeks.mockReturnValue({
			data: [
				{
					weeksAgo: 0,
					hours: 0,
					dailyDurations: {},
					effectiveGoal: 32,
					effectiveGoalType: "target",
					effectiveGoalOverridden: false,
					contractExpected: 25.6,
				},
				{
					weeksAgo: 1,
					weekStart: "2026-08-31",
					hours: 8,
					dailyDurations: {},
					effectiveGoal: 32,
					effectiveGoalType: "target",
					effectiveGoalOverridden: false,
					contractExpected: 24,
				},
			],
		});
		renderPage();

		const history = await screen.findByRole("region", { name: /week history/i });
		expect(within(history).getByText("—/25.6h")).toHaveAttribute(
			"title",
			expect.stringMatching(/after holidays and absences/),
		);
		expect(within(history).getByText("8.0/24h")).toBeInTheDocument();
		expect(within(history).getByText("-16.0h")).toBeInTheDocument();
		expect(within(history).queryByTitle(/goal override/)).not.toBeInTheDocument();
	});

	it("shows the week a contract starts mid-week as the contract's, with no override to offer", async () => {
		// The first term takes effect on this week's Wednesday. The API resolves
		// the week's goal on the personal path — its Monday is before the term —
		// and there is none; beside it, `contract_expected` is what the three
		// days expect, which is the week card's figure. The row follows the
		// card: contract-set, and no override to offer.
		const monday = getMondayIsoFor(0);
		hooks.useProject.mockReturnValue({
			data: {
				...PROJECT,
				kind: "day_job",
				weeklyGoal: undefined,
				contract: {
					terms: [
						{ effectiveFrom: isoDaysAfter(monday, 2), scheduleType: "custom", weeklyHours: 32 },
					],
					holidayCountry: "CH",
					openingBalanceHours: 0,
				},
			},
			isLoading: false,
			error: null,
		});
		hooks.useProjectWeeks.mockReturnValue({
			data: [
				{
					weeksAgo: 0,
					weekStart: monday,
					hours: 0,
					dailyDurations: {},
					effectiveGoal: null,
					effectiveGoalOverridden: false,
					contractExpected: 19.2,
				},
			],
		});
		hooks.useContractWeek.mockReturnValue({
			data: { weekOf: monday, expected: 19.2, worked: 0, remaining: 19.2, balance: 0, days: [] },
			isLoading: false,
			error: null,
		});
		renderPage();

		const history = await screen.findByRole("region", { name: /week history/i });
		const goal = within(history).getByText("—/19.2h");
		expect(goal).toHaveAttribute("title", expect.stringMatching(/after holidays and absences/));
		expect(goal.closest("button")).toBeNull();
		expect(within(history).queryByTitle(/goal override/)).not.toBeInTheDocument();
	});
});
