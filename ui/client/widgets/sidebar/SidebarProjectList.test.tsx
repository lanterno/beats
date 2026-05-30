import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectWithDuration } from "@/entities/project";
import { SidebarProjectList } from "./SidebarProjectList";

vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return {
		...actual,
		NewProjectDialog: () => null,
	};
});

function project(overrides: Partial<ProjectWithDuration>): ProjectWithDuration {
	return {
		id: "x",
		name: "x",
		color: "#fff",
		archived: false,
		goalOverrides: [],
		totalMinutes: 0,
		weeklyMinutes: 0,
		...overrides,
	} as ProjectWithDuration;
}

function renderList(projects: ProjectWithDuration[]) {
	return render(
		<MemoryRouter>
			<SidebarProjectList projects={projects} />
		</MemoryRouter>,
	);
}

describe("SidebarProjectList archived handling", () => {
	afterEach(cleanup);

	it("hides archived projects by default", () => {
		renderList([
			project({ id: "a", name: "Alpha" }),
			project({ id: "b", name: "Beta", archived: true }),
		]);
		expect(screen.getByText("Alpha")).toBeInTheDocument();
		expect(screen.queryByText("Beta")).not.toBeInTheDocument();
	});

	it("shows an Archived rail with a toggle when any archived project exists", async () => {
		renderList([
			project({ id: "a", name: "Alpha" }),
			project({ id: "b", name: "Beta", archived: true }),
		]);

		// Toggle is the escape hatch — without it archived projects would be
		// unreachable from the UI between P0.3 and P3.1 (the /projects page).
		const toggle = screen.getByRole("button", { name: /Archived \(1\)/ });
		expect(toggle).toHaveAttribute("aria-expanded", "false");

		await userEvent.click(toggle);
		expect(toggle).toHaveAttribute("aria-expanded", "true");
		expect(screen.getByText("Beta")).toBeInTheDocument();
	});

	it("omits the Archived rail entirely when no archived projects exist", () => {
		renderList([project({ id: "a", name: "Alpha" })]);
		expect(screen.queryByText(/Archived \(/)).not.toBeInTheDocument();
	});
});
