/**
 * The owner scope over the one timeline (docs/organisations-roadmap.md,
 * stage 2): the pills appear once an organisation's project is in the list,
 * "Personal" leaves only the personal projects' sessions, an organisation's
 * pill only its own, and a note on an organisation's project says the
 * organisation can read it where a personal note says nothing.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProjectWithDuration } from "@/entities/project";
import type { Session } from "@/entities/session";
import { TodayFeed } from "./TodayFeed";

const { hooks } = vi.hoisted(() => ({
	hooks: {
		today: vi.fn<() => Session[]>(() => []),
		projects: vi.fn<() => ProjectWithDuration[]>(() => []),
		deleteSession: vi.fn(),
	},
}));

vi.mock("@/entities/session", async () => {
	const actual = await vi.importActual<typeof import("@/entities/session")>("@/entities/session");
	return {
		...actual,
		useTodaySessions: () => ({ data: hooks.today() }),
		useThisWeekSessions: () => ({ data: [] }),
		useGaps: () => ({ data: [] }),
		useDeleteSession: () => ({ mutate: hooks.deleteSession, isPending: false }),
	};
});
vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return { ...actual, useProjects: () => ({ data: hooks.projects() }) };
});
vi.mock("@/entities/intelligence", () => ({
	useFocusScores: () => ({ data: [] }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function project(overrides: Partial<ProjectWithDuration>): ProjectWithDuration {
	return {
		id: "x",
		name: "x",
		color: "#888",
		archived: false,
		goalOverrides: [],
		autostartRepos: [],
		kind: "side_project",
		totalMinutes: 0,
		weeklyMinutes: 0,
		...overrides,
	};
}

const PROJECTS: ProjectWithDuration[] = [
	project({ id: "mine", name: "Garden" }),
	project({
		id: "work",
		name: "Backend",
		kind: "day_job",
		organisation: { id: "o1", name: "Acme", sharedFrom: "2026-03-04T00:00:00Z" },
	}),
];

/** A finished session earlier today. */
function session(id: string, projectId: string, hoursAgo: number, note?: string): Session {
	const end = new Date(Date.now() - hoursAgo * 3_600_000);
	const start = new Date(end.getTime() - 30 * 60_000);
	return {
		id,
		projectId,
		startTime: start.toISOString(),
		endTime: end.toISOString(),
		duration: 30,
		note,
		tags: [],
	};
}

async function renderFeed(initialEntry = "/app") {
	const { MemoryRouter } = await import("react-router");
	return render(
		<MemoryRouter initialEntries={[initialEntry]}>
			<TodayFeed />
		</MemoryRouter>,
	);
}

describe("TodayFeed — owner scope", () => {
	beforeEach(() => {
		hooks.today.mockReturnValue([]);
		hooks.projects.mockReturnValue(PROJECTS);
	});
	afterEach(cleanup);

	it("offers Everything · Personal · <organisation>, and Personal leaves the organisation's session out", async () => {
		hooks.today.mockReturnValue([
			session("s1", "mine", 3, "weeding"),
			session("s2", "work", 1, "deploy"),
		]);
		await renderFeed();

		const group = screen.getByRole("group", { name: "Filter activity by owner" });
		expect(within(group).getByRole("button", { name: "Everything" })).toHaveAttribute(
			"aria-pressed",
			"true",
		);
		expect(within(group).getByRole("button", { name: "Acme" })).toBeInTheDocument();
		expect(screen.getByText("Garden")).toBeInTheDocument();
		expect(screen.getByText("Backend")).toBeInTheDocument();

		await userEvent.click(within(group).getByRole("button", { name: "Personal" }));
		expect(screen.getByText("Garden")).toBeInTheDocument();
		expect(screen.queryByText("Backend")).not.toBeInTheDocument();

		await userEvent.click(within(group).getByRole("button", { name: "Acme" }));
		expect(screen.queryByText("Garden")).not.toBeInTheDocument();
		expect(screen.getByText("Backend")).toBeInTheDocument();
	});

	it("reads the scope from ?owner= on arrival", async () => {
		hooks.today.mockReturnValue([session("s1", "mine", 3), session("s2", "work", 1)]);
		await renderFeed("/app?owner=o1");

		expect(screen.getByRole("button", { name: "Acme" })).toHaveAttribute("aria-pressed", "true");
		expect(screen.queryByText("Garden")).not.toBeInTheDocument();
		expect(screen.getByText("Backend")).toBeInTheDocument();
	});

	it("marks a note on an organisation's project as readable by it, and a personal note not", async () => {
		hooks.today.mockReturnValue([
			session("s1", "mine", 3, "weeding"),
			session("s2", "work", 1, "deploy"),
		]);
		await renderFeed();

		const markers = screen.getAllByText(/can read this note/);
		expect(markers).toHaveLength(1);
		expect(markers[0]).toHaveTextContent("Acme can read this note");
		// The marker sits with the organisation's note, not the personal one.
		expect(markers[0].parentElement).toHaveTextContent("deploy");
		expect(markers[0].parentElement).not.toHaveTextContent("weeding");
	});

	it("shows no owner pills while every project is personal", async () => {
		hooks.projects.mockReturnValue(PROJECTS.filter((p) => !p.organisation));
		hooks.today.mockReturnValue([session("s1", "mine", 3)]);
		await renderFeed();

		expect(
			screen.queryByRole("group", { name: "Filter activity by owner" }),
		).not.toBeInTheDocument();
	});
});
