import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProjectWithDuration } from "@/entities/project";
import ProjectsIndex from "./ProjectsIndex";

const useProjectsMock = vi.fn();

vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return {
		...actual,
		useProjects: () => useProjectsMock(),
		NewProjectDialog: () => null,
	};
});

function project(overrides: Partial<ProjectWithDuration>): ProjectWithDuration {
	return {
		id: "x",
		name: "x",
		description: undefined,
		color: "#888",
		archived: false,
		goalOverrides: [],
		autostartRepos: [],
		totalMinutes: 0,
		weeklyMinutes: 0,
		...overrides,
	} as ProjectWithDuration;
}

const PROJECTS: ProjectWithDuration[] = [
	project({
		id: "alpha",
		name: "Alpha",
		description: "first project",
		weeklyMinutes: 60,
		lastTrackedAt: "2026-05-30T10:00:00Z",
	}),
	project({
		id: "beta",
		name: "Beta",
		weeklyMinutes: 300,
		lastTrackedAt: "2026-05-29T10:00:00Z",
	}),
	project({
		id: "gamma",
		name: "Gamma",
		weeklyMinutes: 0,
		lastTrackedAt: undefined,
	}),
];

function renderPage() {
	return render(
		<MemoryRouter>
			<ProjectsIndex />
		</MemoryRouter>,
	);
}

describe("ProjectsIndex", () => {
	beforeEach(() => {
		useProjectsMock.mockReturnValue({ data: PROJECTS, isLoading: false });
	});
	afterEach(cleanup);

	it("defaults to sorting by weekly minutes desc", () => {
		renderPage();
		const rows = within(screen.getByRole("table")).getAllByRole("row");
		// First row is the header. Subsequent rows are data, in our sort order.
		const dataRows = rows.slice(1);
		expect(dataRows[0]).toHaveTextContent("Beta");
		expect(dataRows[1]).toHaveTextContent("Alpha");
		expect(dataRows[2]).toHaveTextContent("Gamma");
	});

	it("toggles direction when clicking the same column header twice", async () => {
		renderPage();
		const nameHeader = screen.getByRole("button", { name: /Project/ });
		// First click → sort by name asc (the default for name).
		await userEvent.click(nameHeader);
		let dataRows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
		expect(dataRows[0]).toHaveTextContent("Alpha");
		expect(dataRows[1]).toHaveTextContent("Beta");
		expect(dataRows[2]).toHaveTextContent("Gamma");
		// Second click → reverse.
		await userEvent.click(nameHeader);
		dataRows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
		expect(dataRows[0]).toHaveTextContent("Gamma");
		expect(dataRows[1]).toHaveTextContent("Beta");
		expect(dataRows[2]).toHaveTextContent("Alpha");
	});

	it("filters by the search input across name + description", async () => {
		renderPage();
		const input = screen.getByLabelText("Search projects");
		await userEvent.type(input, "first");
		// Description match → Alpha only.
		const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
		expect(rows).toHaveLength(1);
		expect(rows[0]).toHaveTextContent("Alpha");
	});

	it("shows the no-projects zero-state when there are none", () => {
		useProjectsMock.mockReturnValue({ data: [], isLoading: false });
		renderPage();
		expect(screen.getByText("No projects yet")).toBeInTheDocument();
	});

	it("shows the no-match copy when search returns nothing but visible projects exist", async () => {
		renderPage();
		await userEvent.type(screen.getByLabelText("Search projects"), "zzz-no-such-project");
		expect(screen.getByText(/No projects match your search/)).toBeInTheDocument();
	});
});
