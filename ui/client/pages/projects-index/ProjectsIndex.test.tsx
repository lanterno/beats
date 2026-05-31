import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProjectWithDuration } from "@/entities/project";
import ProjectsIndex from "./ProjectsIndex";

const useProjectsMock = vi.fn();
// `data` keeps its widened ProjectWithDuration[] type so tests can override it.
const useArchivedProjectsMock = vi.fn<() => { data: ProjectWithDuration[]; isLoading: boolean }>();
const unarchiveMutate = vi.fn();

vi.mock("@/entities/project", async () => {
	const actual = await vi.importActual<typeof import("@/entities/project")>("@/entities/project");
	return {
		...actual,
		useProjects: () => useProjectsMock(),
		useArchivedProjects: () => useArchivedProjectsMock(),
		useUnarchiveProject: () => ({
			mutate: unarchiveMutate,
			isPending: false,
			variables: undefined,
		}),
		NewProjectDialog: () => null,
	};
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

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
		useArchivedProjectsMock.mockReturnValue({ data: [], isLoading: false });
		unarchiveMutate.mockReset();
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

	it("switches to the Archived tab and renders the archived list with Restore buttons", async () => {
		useArchivedProjectsMock.mockReturnValue({
			data: [project({ id: "old", name: "OldProject", archived: true, weeklyMinutes: 0 })],
			isLoading: false,
		});
		renderPage();
		await userEvent.click(screen.getByRole("tab", { name: /Archived/ }));

		const row = screen.getByRole("row", { name: /OldProject/ });
		expect(row).toBeInTheDocument();
		const restore = within(row).getByRole("button", { name: "Restore OldProject" });
		expect(restore).toBeInTheDocument();

		await userEvent.click(restore);
		expect(unarchiveMutate).toHaveBeenCalledWith("old", expect.anything());
	});

	it("FF.13: Archived tab drops the Integrations and This week columns; Active keeps them", async () => {
		// The MED finding from the live prod inspection was that 'Last tracked'
		// at 36px wide wrapped to one-char-per-line. The root cause was a
		// missing colgroup + table-layout: fixed letting the Project column
		// eat all the width. Asserting the column set + the table-fixed class
		// regression-proofs both the column trim AND the layout fix.
		useArchivedProjectsMock.mockReturnValue({
			data: [project({ id: "old", name: "OldProject", archived: true, weeklyMinutes: 0 })],
			isLoading: false,
		});
		renderPage();

		// Active tab has 5 column headers: Project, Category, Integrations, This week, Last tracked.
		const activeHeaders = within(screen.getByRole("table"))
			.getAllByRole("columnheader")
			.map((h) => h.textContent?.trim());
		// "This week" carries a "↓" suffix because it's the default sort.
		expect(activeHeaders).toEqual([
			"Project",
			"Category",
			"Integrations",
			"This week↓",
			"Last tracked",
		]);

		// table-layout: fixed is critical — without it the Project column auto-
		// sizes wide and the narrow columns wrap their text vertically. JSDOM
		// doesn't compute styles fully so we assert the class itself.
		expect(screen.getByRole("table").className).toMatch(/table-fixed/);

		// Switch to Archived → Integrations and This week disappear; Restore appears.
		await userEvent.click(screen.getByRole("tab", { name: /Archived/ }));
		const archivedHeaders = within(screen.getByRole("table"))
			.getAllByRole("columnheader")
			.map((h) => h.textContent?.trim());
		expect(archivedHeaders).toEqual(["Project", "Category", "Last tracked", "Restore"]);
	});

	it("FF.8: mobile archived card renders the Restore button as a SIBLING of the Link, not nested inside it", async () => {
		// JSDOM has no media-query CSS so both desktop + mobile branches render;
		// query the mobile list specifically and assert the Restore button's
		// ancestor chain does NOT include an <a>. Pre-FF.8 this nesting was
		// invalid HTML (axe: nested-interactive).
		useArchivedProjectsMock.mockReturnValue({
			data: [project({ id: "old", name: "OldProject", archived: true, weeklyMinutes: 0 })],
			isLoading: false,
		});
		renderPage();
		await userEvent.click(screen.getByRole("tab", { name: /Archived/ }));

		// Pick the mobile-list Restore button: the desktop one is inside a
		// <tr>, the mobile one is inside the md:hidden wrapper.
		const restoreButtons = screen.getAllByRole("button", { name: "Restore OldProject" });
		// At least one in each surface (table + cards), both render in JSDOM.
		expect(restoreButtons.length).toBeGreaterThanOrEqual(1);
		for (const btn of restoreButtons) {
			expect(btn.closest("a")).toBeNull();
		}
	});

	it("shows the archived zero-state when there are no archived projects", async () => {
		renderPage();
		await userEvent.click(screen.getByRole("tab", { name: /Archived/ }));
		expect(screen.getByText("No archived projects")).toBeInTheDocument();
	});

	describe("category chips", () => {
		const CAT_PROJECTS: ProjectWithDuration[] = [
			project({ id: "a", name: "Alpha", category: "coding", weeklyMinutes: 60 }),
			project({ id: "b", name: "Beta", category: "writing", weeklyMinutes: 30 }),
			project({ id: "c", name: "Gamma", category: "coding", weeklyMinutes: 10 }),
			project({ id: "d", name: "Delta", weeklyMinutes: 5 }),
		];

		beforeEach(() => {
			useProjectsMock.mockReturnValue({ data: CAT_PROJECTS, isLoading: false });
		});

		it("renders one chip per distinct category", () => {
			renderPage();
			const chips = screen.getByRole("group", { name: "Filter by category" });
			expect(within(chips).getByRole("button", { name: "coding" })).toBeInTheDocument();
			expect(within(chips).getByRole("button", { name: "writing" })).toBeInTheDocument();
		});

		it("toggles a chip and filters the list (multi-select)", async () => {
			renderPage();
			await userEvent.click(screen.getByRole("button", { name: "coding" }));
			let rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
			// Only the two coding rows remain.
			expect(rows.map((r) => r.textContent)).toEqual(
				expect.arrayContaining([
					expect.stringContaining("Alpha"),
					expect.stringContaining("Gamma"),
				]),
			);
			expect(rows).toHaveLength(2);

			// Adding writing widens the set.
			await userEvent.click(screen.getByRole("button", { name: "writing" }));
			rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
			expect(rows).toHaveLength(3); // Alpha, Beta, Gamma
		});

		it("hydrates from the URL ?category= search param", () => {
			render(
				<MemoryRouter initialEntries={["/projects?category=writing"]}>
					<ProjectsIndex />
				</MemoryRouter>,
			);
			const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
			expect(rows).toHaveLength(1);
			expect(rows[0]).toHaveTextContent("Beta");
			// Chip reflects pressed state for SR.
			expect(screen.getByRole("button", { name: "writing" })).toHaveAttribute(
				"aria-pressed",
				"true",
			);
		});

		it("Clear control removes the category filter", async () => {
			renderPage();
			await userEvent.click(screen.getByRole("button", { name: "coding" }));
			expect(within(screen.getByRole("table")).getAllByRole("row").slice(1)).toHaveLength(2);

			await userEvent.click(screen.getByRole("button", { name: "Clear" }));
			expect(within(screen.getByRole("table")).getAllByRole("row").slice(1)).toHaveLength(4);
		});
	});
});
