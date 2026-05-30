/**
 * Tests for project query hooks — specifically the cache-after-mutation
 * behavior. useProject derives the detail from the cached project list, so a
 * goal-override / project update must leave the detail reflecting the saved
 * value promptly (not the pre-save value until a full reload).
 *
 * We mock ./projectApi so the "server" value is controllable, drive the real
 * TanStack Query cache, and assert the detail tracks the mutation result.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiProject } from "@/shared/api";

vi.mock("./projectApi", () => ({
	fetchProjects: vi.fn(),
	fetchProjectTotal: vi.fn(() => Promise.resolve(0)),
	fetchProjectWeek: vi.fn(() =>
		Promise.resolve({
			totalHours: 0,
			dailyDurations: {},
			weekStart: undefined,
			effectiveGoal: undefined,
			effectiveGoalType: undefined,
			effectiveGoalOverridden: false,
		}),
	),
	updateProject: vi.fn(),
	updateGoalOverrides: vi.fn(),
}));

import { fetchProjects, updateGoalOverrides, updateProject } from "./projectApi";
import { useProject, useProjects, useUpdateGoalOverrides, useUpdateProject } from "./queries";

const PROJECT_ID = "proj-1";

function apiProject(weeklyGoal: number): ApiProject {
	return {
		id: PROJECT_ID,
		name: "Deep Work",
		description: null,
		color: "#FBBF24",
		archived: false,
		estimation: null,
		weekly_goal: weeklyGoal,
		goal_type: "target",
		goal_overrides: [],
		autostart_repos: [],
	};
}

let queryClient: QueryClient;

function wrapper({ children }: { children: ReactNode }) {
	return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

/**
 * Harness that renders the list (to seed its cache), the detail, and exposes
 * both mutation hooks. The detail's weekly goal is printed so the test can
 * observe what the user would see.
 */
function Harness({ onMutations }: { onMutations: (m: Mutations) => void }) {
	useProjects(); // populate the list cache the detail derives from
	const { data: detail } = useProject(PROJECT_ID);
	const updateOverrides = useUpdateGoalOverrides();
	const update = useUpdateProject();
	onMutations({ updateOverrides, update });
	return <div data-testid="detail-goal">{detail ? String(detail.weeklyGoal) : "loading"}</div>;
}

interface Mutations {
	updateOverrides: ReturnType<typeof useUpdateGoalOverrides>;
	update: ReturnType<typeof useUpdateProject>;
}

beforeEach(() => {
	queryClient = new QueryClient({
		defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
	});
});

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe("useProject detail after a mutation", () => {
	it("reflects the saved goal after useUpdateGoalOverrides (no stale value)", async () => {
		// Server starts at goal 5; the list+detail derive from it.
		(fetchProjects as ReturnType<typeof vi.fn>).mockResolvedValue([apiProject(5)]);
		(updateGoalOverrides as ReturnType<typeof vi.fn>).mockResolvedValue(apiProject(10));

		let mutations: Mutations | undefined;
		render(<Harness onMutations={(m) => (mutations = m)} />, { wrapper });

		await screen.findByText("5");

		// The save lands on the server: subsequent list fetches return goal 10.
		(fetchProjects as ReturnType<typeof vi.fn>).mockResolvedValue([apiProject(10)]);

		await act(async () => {
			await mutations?.updateOverrides.mutateAsync({ projectId: PROJECT_ID, overrides: [] });
		});

		// The detail must show the fresh value promptly, not the stale 5.
		await waitFor(() => {
			expect(screen.getByTestId("detail-goal")).toHaveTextContent("10");
		});
	});

	it("reflects the saved value after useUpdateProject", async () => {
		(fetchProjects as ReturnType<typeof vi.fn>).mockResolvedValue([apiProject(3)]);
		(updateProject as ReturnType<typeof vi.fn>).mockResolvedValue(apiProject(7));

		let mutations: Mutations | undefined;
		render(<Harness onMutations={(m) => (mutations = m)} />, { wrapper });

		await screen.findByText("3");

		(fetchProjects as ReturnType<typeof vi.fn>).mockResolvedValue([apiProject(7)]);

		await act(async () => {
			await mutations?.update.mutateAsync({ id: PROJECT_ID, name: "Deep Work" });
		});

		await waitFor(() => {
			expect(screen.getByTestId("detail-goal")).toHaveTextContent("7");
		});
	});
});
